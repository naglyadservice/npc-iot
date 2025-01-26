npc-iot is a Python class designed to facilitate communication with NPC controllers that operate via the MQTT protocol. This library provides an easy-to-use interface to send commands, receive data, and manage device configurations following NPC's protocol specifications.
Features

    Seamless interaction with NPC controllers using MQTT.
    Support for sending commands and retrieving device states.
    Configuration management for NPC devices.
    Acknowledgment handling for reliable communication.
    Easy integration with existing IoT infrastructures.

MQTT Topics Overview

The communication between the server and the NPC controllers is structured using MQTT topics with the following conventions:

    Controller to Server Topics (server direction):
    v2/{device_id}/server/#
    The server subscribes to these topics to receive messages from the controllers.

    Server to Controller Topics (client direction):
    v2/{device_id}/client/#
    The controllers subscribe to these topics to receive commands from the server.

Key MQTT Topics and Their Functions
Topic	QoS	Direction	Description
v2/{device_id}/server/begin	1	Controller → Server	Sent when the controller is powered on or reconnected.
v2/{device_id}/client/reboot	2	Server → Controller	Command to reboot the controller.
v2/{device_id}/client/config/set	1	Server → Controller	Send device configuration to the controller.
v2/{device_id}/server/config/ack	1	Controller → Server	Acknowledgment of configuration reception.
v2/{device_id}/client/state/get	1	Server → Controller	Request the current device state.
v2/{device_id}/server/state	1	Controller → Server	Response with the current state of the device.
v2/{device_id}/server/state/info	1	Controller → Server	Periodic updates of device state.
Example Payloads
Controller Startup Message

Topic: v2/{device_id}/server/begin

{
  "time": "12.09.2024T15:26:36",
  "free_memory": 51200,
  "free_eeprom": 51200,
  "cpu_temperature": 42.5,
  "wifi_signal": -67,
  "gsm_signal": -89,
  "active_connection": "wifi"
}

Reboot Command

Topic: v2/{device_id}/client/reboot

{
  "request_id": 234,
  "delay": 400
}

Device State Request

Topic: v2/{device_id}/client/state/get

{
  "request_id": 234,
  "relay": [1],
  "output": [0, 2],
  "input": [],
  "temperature": [],
  "humidity": []
}

Device State Response

Topic: v2/{device_id}/server/state

{
  "request_id": 234,
  "relay": [{"id": 1, "state": true}],
  "output": [{"id": 0, "state": false}, {"id": 2, "state": false}],
  "input": [{"id": 0, "state": false}, {"id": 1, "state": true}],
  "temperature": [{"id": 0, "value": 26.3}],
  "humidity": [{"id": 0, "value": 73.2}]
}


