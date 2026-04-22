async def create_thread(message, name, auto_archive_duration=1440):
    return await message.create_thread(
        name=name,
        auto_archive_duration=auto_archive_duration
    )
