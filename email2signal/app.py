import asyncio
import re
import requests
import json
import logging
import os
import sys
import email
import html2text
import smtplib
import ssl

from typing import Dict
from urllib.parse import urljoin
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import Envelope, Session, SMTP
from email import message_from_bytes
from email.policy import default
from socket import gaierror
from aiosmtpd.smtp import Envelope

def send_mail(host: str, port: int, user: str, password: str, e: Envelope) -> str:
    if host is None or host == "":
        print("send email is disabled because host is not configured")
        return "250 OK"

    context = ssl.create_default_context()

    try:
        server = smtplib.SMTP(host, port)
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(user, password)
        server.sendmail(user, e.rcpt_tos, e.content, e.mail_options, e.rcpt_options)

    except (gaierror, ConnectionRefusedError):
        return "421 Failed to connect to the server. Bad connection settings?"
    except smtplib.SMTPAuthenticationError:
        return "530 Failed to connect to the server. Wrong user/password?"
    except smtplib.SMTPException as e:
        return "554 SMTP error occurred: " + str(e)
    finally:
        server.quit()

    return "250 OK"


def header_decode(header):
    hdr = ""
    for text, encoding in email.header.decode_header(header):
        if isinstance(text, bytes):
            text = text.decode(encoding or "us-ascii")
        hdr += text
    return hdr

class EmailHandler:
    def __init__(self, config: Dict[str, str]):
        self.receiver_regex = re.compile(r"(\+?\d+)@signal.localdomain")
        self.subject_regex = re.compile(r"Subject: (.*)\n")
        self.image_regex = re.compile(
            r'Content-Type: image/png; name=".*"\n+((?:[A-Za-z\d+/]{4}|\n)*(?:[A-Za-z\d+/]{2}==|[A-Za-z\d+/]{3}=)?)'
        )
        self.config = config

    async def handle_RCPT(
        self, server: SMTP, session: Session, envelope: Envelope, address, rcpt_options: list[str]
    ) -> str:
        print("check address", address)
        if "self@signal.localdomain" in address:
            envelope.rcpt_tos.append(self.config["sender_number"].replace("\\", ""))
        elif address.endswith("@" + str(self.config["signal_redirect_domain"])):
            envelope.rcpt_tos.append(self.config["sender_number"].replace("\\", ""))
        # match and process signal number
        elif match := re.search(self.receiver_regex, address):
            try:
                number = match.group(1)
            except TypeError:
                return "500 Malformed receiver address"

            if not address.startswith("+"):
                number = "+" + number

            envelope.rcpt_tos.append(number)
        # simply append normal mail address
        else:
            envelope.rcpt_tos.append(address)

        return "250 OK"

    async def handle_DATA(self, server: SMTP, session: Session, envelope: Envelope) -> str:
        signal_numbers = []
        mail_addresses = []
        for addr in envelope.rcpt_tos:
            # a real email address cannot start with a special char
            if addr.startswith("+"):
                signal_numbers.append(addr)
            else:
                mail_addresses.append(addr)

        # send signal message if required
        if len(signal_numbers) > 0:
            print("Forwarding message to signal: {}".format(signal_numbers))
            success = await self.send_signal(envelope, signal_numbers)

            if not success:
                return "554 Sending signal message has failed"

        # send email if required
        if len(mail_addresses) == 0:
            return "250 Message accepted for delivery"
        else:
            envelope.rcpt_tos = mail_addresses

            print(f"Sending email via MTA. From: {envelope.mail_from} To: {envelope.rcpt_tos}")
            return send_mail(
                self.config["smtp_host"],
                int(self.config["smtp_port"]),
                self.config["smtp_user"],
                self.config["smtp_passwd"],
                envelope,
            )

    async def send_signal(self, envelope: Envelope, signal_receivers: list[str]) -> bool:
        mail = message_from_bytes(envelope.content, policy=default)
        body = mail.get_body(('html', 'plain'))
        if body:
            body = body.get_content()
        print("body", body)
        
        payload = {}
        
        msg = str(header_decode(mail.get('Subject'))) + "\r\n"

        if all(x in body for x in ["<!DOCTYPE html "]):
            html = "<!DOCTYPE html " + body.split('<!DOCTYPE html ', 1)[-1]
            msg += html2text.html2text(html)
        else:
            # assume it is a plain text email
            msg += body

        msg = str(msg)

        payload["message"] = msg
        payload["number"] = self.config["sender_number"].replace("\\", "")
        payload["recipients"] = signal_receivers

        headers = {"Content-Type": "application/json"}

        url = urljoin(self.config["signal_rest_url"], "v2/send")

        print("url:", url)
        print("header:", headers)
        print("payload:", payload)

        if ignored := os.getenv("SIGNAL_REDIRECT_CONTENT_FILTER"):
            if any(x in msg for x in ignored.split(',') if len(x) > 2):
                print("Message contains filtered content, do not redirect message to signal")
                return True

        response = requests.request("POST", url, headers=headers, data=json.dumps(payload))

        print("response:", response.status_code)

        if response.status_code == 201:
            return True
        else:
            return False


async def amain(loop: asyncio.AbstractEventLoop):
    try:
        config = {
            "signal_rest_url": os.environ["SIGNAL_REST_URL"],
            "signal_redirect_domain": os.environ["SIGNAL_REDIRECT_DOMAIN"],
            "sender_number": os.environ["SENDER_NUMBER"],
            "smtp_host": os.environ["SMTP_HOST"],
            "smtp_user": os.environ["SMTP_USER"],
            "smtp_passwd": os.environ["SMTP_PASSWORD"],
            "smtp_port": os.getenv("SMTP_PORT", "587"),
        }
    except KeyError:
        sys.exit("Please set the required environment variables.")

    print("Starting email2signal server")
    email_handler = EmailHandler(config)
    controller = Controller(email_handler, hostname="")
    controller.start()


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.WARNING)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True
    loop = asyncio.get_event_loop()
    loop.create_task(amain(loop=loop))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
