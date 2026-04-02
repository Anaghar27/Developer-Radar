import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_reset_email(to_email: str, token: str) -> bool:
    """
    Send a password reset email.
    Returns True if sent via SMTP, False if SMTP is not configured (dev mode).
    When False, the token is logged so local dev still works.
    """
    smtp_host = os.getenv("SMTP_HOST", "")
    if not smtp_host:
        logger.info("SMTP not configured — reset token for %s: %s", to_email, token)
        return False

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("SMTP_FROM", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = "Your DevPulse password reset OTP"

    plain = (
        f"Hi,\n\n"
        f"We received a request to reset the password for your DevPulse account.\n\n"
        f"Your one-time password (OTP) is:\n\n"
        f"  {token}\n\n"
        f"This OTP expires in 5 minutes. Enter it on the Reset Password screen to set a new password.\n\n"
        f"If you didn't request this, no action is needed — your account is safe.\n\n"
        f"Thanks,\n"
        f"The DevPulse Team"
    )

    html = f"""\
<html>
  <body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 0;">
      <tr>
        <td align="center">
          <table width="480" cellpadding="0" cellspacing="0"
                 style="background:#ffffff;border-radius:8px;overflow:hidden;
                        box-shadow:0 2px 8px rgba(0,0,0,0.08);">

            <!-- Header -->
            <tr>
              <td style="background:#1a1a2e;padding:28px 32px;">
                <p style="margin:0;font-size:22px;font-weight:700;color:#ffffff;
                           letter-spacing:1px;">📡 DevPulse</p>
                <p style="margin:4px 0 0;font-size:12px;color:#a0aec0;">
                  Real-Time Developer Sentiment Intelligence
                </p>
              </td>
            </tr>

            <!-- Body -->
            <tr>
              <td style="padding:36px 32px 24px;">
                <p style="margin:0 0 8px;font-size:18px;font-weight:600;color:#1a202c;">
                  Password Reset Request
                </p>
                <p style="margin:0 0 24px;font-size:14px;color:#4a5568;line-height:1.6;">
                  We received a request to reset the password for your DevPulse account.
                  Use the OTP below to proceed.
                </p>

                <!-- OTP box -->
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td align="center"
                        style="background:#f0f4ff;border:2px dashed #4a6cf7;
                               border-radius:8px;padding:20px;">
                      <p style="margin:0 0 4px;font-size:12px;color:#4a5568;
                                 text-transform:uppercase;letter-spacing:1px;">
                        Your One-Time Password
                      </p>
                      <p style="margin:0;font-size:36px;font-weight:700;
                                 letter-spacing:10px;color:#1a1a2e;">
                        {token}
                      </p>
                    </td>
                  </tr>
                </table>

                <p style="margin:24px 0 0;font-size:13px;color:#718096;line-height:1.6;">
                  ⏱ This OTP expires in <strong>5 minutes</strong>.<br>
                  Enter it on the Reset Password screen to set a new password.
                </p>
              </td>
            </tr>

            <!-- Divider -->
            <tr>
              <td style="padding:0 32px;">
                <hr style="border:none;border-top:1px solid #e2e8f0;margin:0;">
              </td>
            </tr>

            <!-- Footer -->
            <tr>
              <td style="padding:20px 32px 32px;">
                <p style="margin:0;font-size:12px;color:#a0aec0;line-height:1.6;">
                  If you didn't request a password reset, you can safely ignore this email —
                  your account remains secure.<br><br>
                  &copy; DevPulse
                </p>
              </td>
            </tr>

          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to_email, msg.as_string())
        logger.info("Reset email sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send reset email to %s", to_email)
        return False
