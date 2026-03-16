"""
email_report.py  –  Send the GM VIP consolidated test report via e-mail
========================================================================
Works in two modes that are transparent to the caller:

  Local (standalone)  –  configure via a ``.env`` file next to this script
                         or by exporting environment variables in your shell.

  Jenkins pipeline    –  Jenkins sets the same environment variables through
                         node environment settings or credentials bindings;
                         call this script at the end of the pipeline's
                         ``post { always { ... } }`` block.

Environment variables
---------------------
  EMAIL_SMTP_HOST      SMTP server hostname           (default: localhost)
  EMAIL_SMTP_PORT      SMTP port                      (default: 587)
  EMAIL_SMTP_USER      Username / "From" address
  EMAIL_SMTP_PASS      Password (use Jenkins credentials or OS keyring)
  EMAIL_USE_TLS        Use STARTTLS (true/false)      (default: true)
  EMAIL_USE_SSL        Use port-465 SSL (true/false)  (default: false)
  EMAIL_RECIPIENTS     Comma-separated recipient list
  EMAIL_FROM_NAME      Friendly display name          (default: GM VIP Automation)
  BUILD_NUMBER         Build/run number for the subject line  (Jenkins sets automatically)
  JOB_NAME             Pipeline name                  (Jenkins sets automatically)
  BUILD_URL            Link back to the Jenkins build (Jenkins sets automatically)

Usage
-----
  python email_report.py --report <path/to/merged_report.html>
                         [--subject "Custom subject line"]
                         [--recipients "a@corp.com,b@corp.com"]
                         [--dry-run]

  --dry-run   Print the message headers and a body preview without
              connecting to any SMTP server.  Use this to validate
              configuration without actually sending e-mail.

Exit codes
----------
  0  – message sent (or dry-run completed) successfully
  1  – configuration error or SMTP failure (details printed to stderr)
"""

from __future__ import annotations

import argparse
import email.mime.base
import email.mime.multipart
import email.mime.text
import os
import smtplib
import ssl
import sys
from email import encoders
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def _load_dotenv(env_path: Optional[Path] = None) -> None:
    """Load key=value pairs from a .env file into os.environ.

    Only lines of the form ``KEY=VALUE`` (no leading ``export``) are read.
    Existing environment variables are **not** overwritten so that shell
    exports and Jenkins environment variables always take precedence.

    The function is silent if the file does not exist.
    """
    path = env_path or (Path(__file__).parent / ".env")
    if not path.is_file():
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _bool_env(name: str, default: bool = False) -> bool:
    """Return the boolean value of an environment variable."""
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default


def _recipients_from_env() -> List[str]:
    raw = os.environ.get("EMAIL_RECIPIENTS", "")
    return [r.strip() for r in raw.split(",") if r.strip()]


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------

def _build_message(
    subject: str,
    recipients: List[str],
    report_path: Optional[Path],
    build_url: str,
    build_number: str,
    job_name: str,
) -> email.mime.multipart.MIMEMultipart:
    """Assemble a MIME multipart message with an HTML body and optional report attachment."""

    from_addr = os.environ.get("EMAIL_SMTP_USER", "gm-vip-automation@example.com")
    from_name = os.environ.get("EMAIL_FROM_NAME", "GM VIP Automation")
    from_header = f"{from_name} <{from_addr}>"

    msg = email.mime.multipart.MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = from_header
    msg["To"]      = ", ".join(recipients)

    # ------------------------------------------------------------------ body
    build_link = (
        f'<a href="{build_url}">{build_url}</a>'
        if build_url
        else "(local run – no URL)"
    )
    run_label = f"#{build_number}" if build_number else "(local)"
    report_note = (
        "The merged HTML report is attached to this e-mail."
        if report_path and report_path.is_file()
        else "No merged report file was found; check the run logs for details."
    )

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <style>
    body   {{ font-family: Arial, sans-serif; color: #333; }}
    table  {{ border-collapse: collapse; margin-top: 12px; }}
    td, th {{ border: 1px solid #ccc; padding: 6px 12px; }}
    th     {{ background: #f0f0f0; text-align: left; }}
    .pass  {{ color: #1a7f37; font-weight: bold; }}
    .fail  {{ color: #cf222e; font-weight: bold; }}
    .info  {{ color: #0550ae; }}
  </style>
</head>
<body>
  <h2>GM VIP Automation – Test Report</h2>
  <table>
    <tr><th>Job</th>      <td class="info">{job_name or "Local Run"}</td></tr>
    <tr><th>Build</th>    <td>{run_label}</td></tr>
    <tr><th>Build URL</th><td>{build_link}</td></tr>
  </table>
  <p>{report_note}</p>
  <p>Open the attached <code>merged_report.html</code> in any web browser to
     browse results with the interactive sidebar, summary cards, and
     step-level failure details.</p>
  <hr>
  <p style="font-size:0.85em; color:#888;">
    Sent by <em>email_report.py</em> – GM VIP Automation pipeline.
  </p>
</body>
</html>
"""
    msg.attach(email.mime.text.MIMEText(html_body, "html", "utf-8"))

    # -------------------------------------------------------------- attachment
    if report_path and report_path.is_file():
        with open(report_path, "rb") as fh:
            part = email.mime.base.MIMEBase("application", "octet-stream")
            part.set_payload(fh.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=report_path.name,
        )
        msg.attach(part)

    return msg


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def send_report(
    report_path: Optional[Path],
    subject: Optional[str],
    extra_recipients: Optional[List[str]],
    dry_run: bool = False,
) -> int:
    """Build and send (or dry-run) the e-mail report.

    Returns 0 on success, 1 on any error.
    """
    smtp_host    = os.environ.get("EMAIL_SMTP_HOST", "localhost")
    smtp_port    = _int_env("EMAIL_SMTP_PORT", 587)
    smtp_user    = os.environ.get("EMAIL_SMTP_USER", "")
    smtp_pass    = os.environ.get("EMAIL_SMTP_PASS", "")
    use_tls      = _bool_env("EMAIL_USE_TLS", default=True)
    use_ssl      = _bool_env("EMAIL_USE_SSL", default=False)
    build_number = os.environ.get("BUILD_NUMBER", "")
    job_name     = os.environ.get("JOB_NAME", "")
    build_url    = os.environ.get("BUILD_URL", "")

    recipients = _recipients_from_env()
    if extra_recipients:
        # --recipients on the CLI replaces EMAIL_RECIPIENTS entirely.
        recipients = extra_recipients
    if not recipients:
        print(
            "ERROR: No recipients configured.  "
            "Set EMAIL_RECIPIENTS or pass --recipients.",
            file=sys.stderr,
        )
        return 1

    run_label = f"#{build_number}" if build_number else "local"
    auto_subject = (
        f"GM VIP Automation – Test Report {run_label}"
        + (f" – {job_name}" if job_name else "")
    )
    final_subject = subject or auto_subject

    msg = _build_message(
        subject=final_subject,
        recipients=recipients,
        report_path=report_path,
        build_url=build_url,
        build_number=build_number,
        job_name=job_name,
    )

    # -------------------------------------------------------------- dry-run
    if dry_run:
        print("=== DRY RUN – message would be sent as follows ===")
        print(f"  SMTP host : {smtp_host}:{smtp_port}  "
              f"(TLS={use_tls}, SSL={use_ssl})")
        print(f"  From      : {msg['From']}")
        print(f"  To        : {msg['To']}")
        print(f"  Subject   : {msg['Subject']}")
        has_att = report_path and report_path.is_file()
        print(f"  Attachment: {report_path.name if has_att else 'none'}")
        print("=== DRY RUN complete – no message was sent ===")
        return 0

    # ------------------------------------------------------------ send email
    if not smtp_user or not smtp_pass:
        print(
            "WARNING: EMAIL_SMTP_USER or EMAIL_SMTP_PASS is not set.  "
            "Attempting unauthenticated connection.",
            file=sys.stderr,
        )

    try:
        context = ssl.create_default_context()
        if use_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user or "gm-vip@localhost", recipients, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if use_tls:
                    server.starttls(context=context)
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user or "gm-vip@localhost", recipients, msg.as_string())

        print(f"Report e-mailed to: {', '.join(recipients)}")
        return 0

    except smtplib.SMTPException as exc:
        print(f"SMTP error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Network error connecting to {smtp_host}:{smtp_port}: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send the GM VIP consolidated test report via e-mail.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration is read from environment variables (set in your shell, a .env
file next to this script, or Jenkins node/pipeline settings):

  EMAIL_SMTP_HOST      SMTP hostname          (default: localhost)
  EMAIL_SMTP_PORT      SMTP port              (default: 587)
  EMAIL_SMTP_USER      Username / from address
  EMAIL_SMTP_PASS      Password
  EMAIL_USE_TLS        true/false             (default: true)
  EMAIL_USE_SSL        true/false             (default: false)
  EMAIL_RECIPIENTS     Comma-separated recipients
  EMAIL_FROM_NAME      Friendly sender name   (default: GM VIP Automation)

Jenkins sets BUILD_NUMBER, JOB_NAME, and BUILD_URL automatically.
""",
    )
    parser.add_argument(
        "--report",
        metavar="HTML_FILE",
        help="Path to the merged_report.html produced by merge_reports.py.",
    )
    parser.add_argument(
        "--subject",
        metavar="TEXT",
        help="Custom e-mail subject line (auto-generated if omitted).",
    )
    parser.add_argument(
        "--recipients",
        metavar="ADDR_LIST",
        help="Comma-separated recipient addresses (overrides EMAIL_RECIPIENTS).",
    )
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        help="Path to a .env file (default: .env next to email_report.py).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print message details without connecting to any SMTP server.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(argv)

    # Load .env before reading any other env vars
    env_file = Path(args.env_file) if args.env_file else None
    _load_dotenv(env_file)

    report_path: Optional[Path] = None
    if args.report:
        report_path = Path(args.report)
        if not report_path.is_file() and not args.dry_run:
            print(
                f"WARNING: report file not found: {report_path}  "
                "(e-mail will be sent without attachment)",
                file=sys.stderr,
            )

    extra_recipients: Optional[List[str]] = None
    if args.recipients:
        extra_recipients = [r.strip() for r in args.recipients.split(",") if r.strip()]

    return send_report(
        report_path=report_path,
        subject=args.subject,
        extra_recipients=extra_recipients,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
