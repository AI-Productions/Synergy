from synergy import SynergyServer

synergy_server = SynergyServer()
synergy_server.create_room('Global', default_room=True)
synergy_server.start()

"""
From a websocket client:

Sent:     {"request": "authenticate", "aid": "c9f93756-2ff6-40aa-8824-2409d7113818"}
Received: {"request": "authenticate", "authenticated": true}
Received: {"rooms": ["Global"], "request": "room_list"}
Sent:     {"request": "send_message", "room": "Global", "message": "Hi"}
Received: {"message": "Hi", "color": "green", "author": "JCharante"}
"""
