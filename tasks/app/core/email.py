from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from smtplib import SMTP
from typing import Any

from fastapi.templating import Jinja2Templates

from core.config import settings


class EmailService:
    """Сервис для подготовки и отправки Email-уведомлений."""

    def __init__(self) -> None:
        self.templates = Jinja2Templates(directory=settings.templates_dir)
        self._username = settings.email_settings.EMAIL_USERNAME
        self._password = settings.email_settings.EMAIL_PASSWORD
        self._host = settings.email_settings.EMAIL_HOST
        self._port = settings.email_settings.EMAIL_PORT

    def _prepare_message(
        self,
        to_email: str,
        subject: str,
        template_name: str,
        context: dict[str, Any],
    ) -> MIMEMultipart:
        """Собрать MIMEMultipart объект и отрендерить HTML-контент."""
        template = self.templates.get_template(name=template_name)
        html_content = template.render(**context)

        message = MIMEMultipart()
        message['From'] = self._username
        message['To'] = to_email
        message['Subject'] = subject
        message.attach(MIMEText(html_content, 'html', 'utf-8'))

        return message

    def _send_raw_mail(self, message: MIMEMultipart) -> None:
        """Отправить подготовленное сообщение через SMTP-сервер."""
        with SMTP(self._host, self._port) as server:
            server.starttls()
            server.login(self._username, self._password)
            server.send_message(message)

    def send_template_email(
        self,
        to_email: str,
        subject: str,
        template_name: str,
        context: dict[str, Any],
    ) -> None:
        """Публичный интерфейс для отправки шаблонных писем."""
        message = self._prepare_message(
            to_email=to_email,
            subject=subject,
            template_name=template_name,
            context=context,
        )
        self._send_raw_mail(message)


email_service = EmailService()
