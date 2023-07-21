from urlextract import URLExtract
from urllib.parse import urlparse

class EditLinkFilter:
    def __init__(self, client, allowed_domains):
        self.client = client
        self.allowed_domains = set(allowed_domains)
        self.extractor = URLExtract()

    async def on_message_edit(self, message_before, message_after):
        if not message_after.edited_at or message_after.author.bot or not message_after.author.joined_at: or \
            message_after.channel.permissions_for(message_after.author).manage_messages or \
            message_after.author.joined_at < (datetime.datetime.now() - timedelta(days=180)):
            return
        urls_after = set(self.extractor.find_urls(message_after.content, True))
        for url in urls_after:
            parsed_url = urlparse(url)
            hostname = parsed_url.hostname
            is_allowed = False
            for allowed in self.allowed_domains:
                if hostname.endswith(allowed):
                    is_allowed = True
                    break
            if is_allowed:
                continue
            await message_after.delete()
            
    