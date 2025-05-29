import asyncio
from pprint import pprint
from typing import Any

DEVICE_ID = "6CA3AC182EC8"
from npc_iot.npc import NpcClient


async def callback(device_id: str, payload: dict[str, Any]):
    print("Received every 1 minute actual state of device:")
    print(device_id, payload)


async def main():
    npc_client = NpcClient(host="mqtt.npc.com.ua", port=1883, username="", password="")

    async with npc_client as npc_client:
        npc_client.dispatcher.state_info.register_callback(callback)

        # Send command to device without waiting for response
        await npc_client.set_state(
            device_id=DEVICE_ID,
            payload={
                "output": [
                    {"id": 1, "state": True},
                    {"id": 2, "state": True, "duration": 1000},
                    {"id": 3, "state": True, "duration": 1000},
                ],
            },
        )

        # Send command to device and wait for response
        waiter = await npc_client.set_state(
            device_id=DEVICE_ID,
            payload={
                "output": [
                    {"id": 1, "state": True},
                ],
            },
        )

        response = await waiter.wait()
        pprint(response)

        # Get state of device and wait for response
        waiter = await npc_client.get_state(
            "6CA3AC182EC8",
            payload={
                "relay": [],
                "output": [],
                "input": [],
                "temperature": [],
                "humidity": [],
            },
        )
        response = await waiter.wait()
        pprint(response)

        # Reboot device and wait for response
        waiter = await npc_client.reboot(DEVICE_ID, payload={"delay": 400})
        response = await waiter.wait()
        print(response)


if __name__ == "__main__":
    asyncio.run(main())
