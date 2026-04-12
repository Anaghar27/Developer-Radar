"""Kafka batch consumer for raw post ingestion."""

import json
import logging
import os
from datetime import UTC, datetime

import psycopg2
from dotenv import load_dotenv
from kafka import KafkaConsumer, KafkaProducer

try:
    from kafka.errors import KafkaError
except ImportError:  # pragma: no cover - test stubs may not expose kafka.errors
    KafkaError = Exception

from processing.validator import coerce_message, validate_post
from storage.db_client import insert_failed_event, insert_raw_post, post_exists

load_dotenv()


logger = logging.getLogger(__name__)

RAW_POSTS_TOPIC = "raw_posts"
FAILED_EVENTS_TOPIC = "failed_events"


def get_consumer() -> KafkaConsumer:
    """Create and return the batch Kafka consumer."""
    return KafkaConsumer(
        RAW_POSTS_TOPIC,
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        group_id="devpulse_consumer_group",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        consumer_timeout_ms=10_000,
    )


def get_failed_events_producer() -> KafkaProducer:
    """Create and return the failed events Kafka producer."""
    return KafkaProducer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        retries=3,
    )


def route_failed_event(
    failed_producer: KafkaProducer,
    original_message: dict,
    error_reason: str,
    ingest_batch_id: str,
) -> None:
    """Publish and persist a failed ingestion event."""
    failed_event = {
        "event_type": "ingestion",
        "payload": original_message,
        "error_reason": error_reason,
        "ingest_batch_id": ingest_batch_id,
    }

    try:
        failed_producer.send(FAILED_EVENTS_TOPIC, value=failed_event)
    except KafkaError as exc:
        logger.error(
            "Failed to publish invalid message to Kafka failed_events topic | "
            "batch_id=%s | error_type=%s | error=%s",
            ingest_batch_id,
            type(exc).__name__,
            exc,
        )
    except Exception as exc:
        # Catch-all for truly unexpected Kafka routing failures.
        logger.exception(
            "Unexpected failure publishing invalid message to Kafka failed_events topic | "
            "batch_id=%s | error_type=%s | error=%s",
            ingest_batch_id,
            type(exc).__name__,
            exc,
        )

    try:
        insert_failed_event("ingestion", original_message, error_reason)
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as exc:
        logger.error(
            "Failed to persist invalid message to failed_events table | "
            "batch_id=%s | error_type=%s | error=%s",
            ingest_batch_id,
            type(exc).__name__,
            exc,
        )
    except Exception as exc:
        # Catch-all for truly unexpected failed-events persistence issues.
        logger.exception(
            "Unexpected failure persisting invalid message to failed_events table | "
            "batch_id=%s | error_type=%s | error=%s",
            ingest_batch_id,
            type(exc).__name__,
            exc,
        )


def build_post_record(message: dict) -> dict:
    """Map a validated Kafka message into the raw_posts insert shape."""
    post = dict(message)
    created_utc = message.get("created_utc", 0)
    post["created_at"] = datetime.fromtimestamp(float(created_utc), UTC)
    return post


def run(ingest_batch_id: str) -> dict:
    """
    Consume all messages from raw_posts topic for this batch.
    For each message:
      1. coerce_message()
      2. validate_post()
      3a. If valid and not already in DB -> insert_raw_post()
      3b. If valid but duplicate -> log and skip (counted as duplicate)
      3c. If invalid -> publish to failed_events Kafka topic + insert_failed_event()

    Returns a summary dict:
    {
        "total_consumed": int,
        "inserted": int,
        "duplicates": int,
        "failed": int,
    }
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    summary = {
        "total_consumed": 0,
        "inserted": 0,
        "duplicates": 0,
        "failed": 0,
    }

    consumer = get_consumer()
    failed_producer = get_failed_events_producer()

    try:
        for record in consumer:
            original_message = record.value
            summary["total_consumed"] += 1
            post_id = None

            try:
                coerced_message = coerce_message(original_message)
                post_id = coerced_message.get("id")
                is_valid, error_reason = validate_post(coerced_message)

                if not is_valid:
                    summary["failed"] += 1
                    route_failed_event(
                        failed_producer,
                        original_message,
                        error_reason,
                        ingest_batch_id,
                    )
                    continue

                if post_exists(coerced_message["id"]):
                    summary["duplicates"] += 1
                    logger.info("Skipping duplicate raw post: %s", coerced_message["id"])
                    continue

                post_record = build_post_record(coerced_message)
                post_record["ingest_batch_id"] = ingest_batch_id

                try:
                    insert_raw_post(post_record)
                    summary["inserted"] += 1
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as exc:
                    summary["failed"] += 1
                    error_reason = f"PostgreSQL insert failed: {exc}"
                    logger.error(
                        "DB insert failed | post_id=%s | batch_id=%s | "
                        "error_type=%s | error=%s",
                        post_id,
                        ingest_batch_id,
                        type(exc).__name__,
                        exc,
                    )
                    route_failed_event(
                        failed_producer,
                        original_message,
                        error_reason,
                        ingest_batch_id,
                    )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                summary["failed"] += 1
                error_reason = f"Message parse failed: {exc}"
                logger.error(
                    "Message parse failed | post_id=%s | batch_id=%s | "
                    "error_type=%s | error=%s",
                    post_id,
                    ingest_batch_id,
                    type(exc).__name__,
                    exc,
                )
                route_failed_event(
                    failed_producer,
                    original_message if isinstance(original_message, dict) else {},
                    error_reason,
                    ingest_batch_id,
                )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as exc:
                summary["failed"] += 1
                error_reason = f"Database error while processing message: {exc}"
                logger.error(
                    "DB processing failed | post_id=%s | batch_id=%s | "
                    "error_type=%s | error=%s",
                    post_id,
                    ingest_batch_id,
                    type(exc).__name__,
                    exc,
                )
                route_failed_event(
                    failed_producer,
                    original_message if isinstance(original_message, dict) else {},
                    error_reason,
                    ingest_batch_id,
                )
            except Exception as exc:
                # Catch-all for truly unexpected consumer processing errors.
                summary["failed"] += 1
                error_reason = f"Unexpected consumer processing error: {exc}"
                logger.exception(
                    "Unexpected error processing message | post_id=%s | batch_id=%s | "
                    "error_type=%s | error=%s",
                    post_id,
                    ingest_batch_id,
                    type(exc).__name__,
                    exc,
                )
                route_failed_event(
                    failed_producer,
                    original_message if isinstance(original_message, dict) else {},
                    error_reason,
                    ingest_batch_id,
                )
    finally:
        failed_producer.flush()
        failed_producer.close()
        consumer.close()

    return summary


def consume_failed_events(ingest_batch_id: str) -> int:
    """
    Dead letter consumer — reads from failed_events Kafka topic
    and persists each message to the failed_events PostgreSQL table.

    Returns number of failed events written to DB.
    """
    dl_consumer = KafkaConsumer(
        "failed_events",
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        group_id="devpulse_dead_letter_group",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        consumer_timeout_ms=5_000,
    )
    inserted_count = 0

    try:
        for record in dl_consumer:
            message = record.value
            try:
                insert_failed_event(
                    event_type=message["event_type"],
                    payload=message["payload"],
                    error_reason=message["error_reason"],
                )
                inserted_count += 1
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as exc:
                logger.error(
                    "Failed to persist dead letter event | batch_id=%s | "
                    "error_type=%s | error=%s",
                    ingest_batch_id,
                    type(exc).__name__,
                    exc,
                )
            except (KeyError, TypeError) as exc:
                logger.error(
                    "Dead letter message parse failed | batch_id=%s | "
                    "error_type=%s | error=%s",
                    ingest_batch_id,
                    type(exc).__name__,
                    exc,
                )
            except Exception as exc:
                # Catch-all for truly unexpected dead-letter consumer failures.
                logger.exception(
                    "Unexpected dead letter persistence failure | batch_id=%s | "
                    "error_type=%s | error=%s",
                    ingest_batch_id,
                    type(exc).__name__,
                    exc,
                )
    finally:
        dl_consumer.close()

    return inserted_count
