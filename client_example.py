from synergy import SynergyClient
import asyncio

loop = asyncio.get_event_loop()

synergy_client = SynergyClient('ws://localhost:4545/master', 'c6194232-1372-4659-906d-4815899d7bad')
synergy_client.start_client()

synergy_client.create_room('Dank Memers Convention')

print(synergy_client.get_rooms())
