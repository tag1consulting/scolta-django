"""``manage.py scolta_amazee_provision`` — provision a free Amazee.ai trial."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from scolta.ai.amazee import (
    AmazeeApiException,
    AmazeeClient,
    AmazeeModelResolver,
    AmazeeTrialProvisioner,
)

from ...amazee import DjangoConfigStorage, build_key_expiry_recovery


class Command(BaseCommand):
    help = "Provision a free Amazee.ai trial and store the credentials."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--email", default="", help="Email for the trial (optional; anonymous if omitted)."
        )
        parser.add_argument(
            "--force", action="store_true", help="Provision even if credentials already exist."
        )

    def handle(self, *args, **options) -> None:
        storage = DjangoConfigStorage()
        # If the stored credentials are no longer accepted, tell the operator
        # why AI is degraded and how to reconnect before continuing. Running
        # this command with an email re-establishes the Amazee.ai connection.
        if build_key_expiry_recovery().is_upgrade_needed():
            self.stdout.write(
                self.style.WARNING(
                    "The current Amazee.ai connection is no longer accepted and needs "
                    "re-authentication. AI search features are degraded until you reconnect."
                )
            )
            self.stdout.write(
                "Reconnect by running this command with an email, or from the Scolta "
                "Amazee.ai settings page."
            )
        if storage.load() is not None and not options["force"]:
            self.stdout.write(
                self.style.WARNING(
                    "Amazee credentials already stored (use --force to re-provision)."
                )
            )
            return
        client = AmazeeClient()
        provisioner = AmazeeTrialProvisioner(client, storage, None, AmazeeModelResolver(client))
        try:
            result = provisioner.provision(options["email"])
        except AmazeeApiException as exc:
            self.stderr.write(self.style.ERROR(f"Provisioning failed: {exc}"))
            raise SystemExit(1) from exc
        if result.ai_model or result.ai_expansion_model:
            storage.store_models(result.ai_model or "", result.ai_expansion_model or "")
        # Fresh credentials are stored — clear any re-authentication prompt.
        build_key_expiry_recovery().clear_upgrade_needed()
        self.stdout.write(
            self.style.SUCCESS(
                f"Provisioned Amazee trial (region {result.region}); models: "
                f"{result.ai_model or '-'} / {result.ai_expansion_model or '-'}"
            )
        )
