from django.core.management.base import BaseCommand

from apps.accounts.models import UserAPIKey
from pipeline.secure import encrypt_string, get_fernet


class Command(BaseCommand):
    help = (
        "Re-encrypt all UserAPIKey rows with the current primary key. "
        "Set FIELD_ENCRYPTION_KEY=new_key,old_key before running, "
        "then remove old_key after completion."
    )

    def handle(self, *args, **options):
        fernet = get_fernet()
        keys = UserAPIKey.objects.select_related("owner", "provider").all()
        count = 0
        for key in keys:
            plaintext = fernet.decrypt(bytes(key._api_key_enc)).decode()
            key._api_key_enc = encrypt_string(plaintext)
            key.save(update_fields=["_api_key_enc", "updated_at"])
            count += 1
            self.stdout.write(f"  Re-encrypted key for {key.owner.email} / {key.provider.code}")

        self.stdout.write(self.style.SUCCESS(
            f"Done — re-encrypted {count} key(s). "
            "Remove the old key from FIELD_ENCRYPTION_KEY now."
        ))
