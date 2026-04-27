 Message Specs

Introduction
Protobufs definition
Queues Naming

Introduction
This document will serve to unify all the documentation regarding the message interchange between the Machines, the Apps and the Server.
Protobufs definition
Refer to the git repo: https://github.com/minibrew/minibrew-protobuf
Queues Naming
There will be several queues between the different parties, here is the list of them and the naming conventions that will be used when creating the queue names. 

The first word of the topic is the originator of the message, the second word will be the type of message that is being sent, while the last word of the topic will be the MAC address of the device without any ‘:’ or ‘-’ symbols.

The keys indicating the originator and receiver of the message are as follow:
? DE: Devices
? AP: App
? BE: Backend
We will use 15-AB-51-0E-93-FA-46 as an example MAC address, formatted to: 15AB510E93FA46 or the Device’s serial number: 1903K0001-ABCD1234.

Here is the full list of topics:
? Commands [BE-DE]: backend/commands/{SerialNumber}
? Command Resp [DE-BE]: devices/commands/{SerialNumber}
? Events [DE-BE]: devices/events/{SerialNumber}
? Event Resp [BE-DE]: backend/events/{SerialNumber}
? Batch Logs [DE-BE]: devices/batchlogs/{SerialNumber}
? Batch Log Resp [BE-DE]: backend/batchlogs/{SerialNumber}
? Frequent Logs [DE-AP]: devices/logs/{SerialNumber}
? Log Request [AP-DE]: apps/logrequests/{		}
? Log Request Resp [DE-AP]: devices/logrequests/{SerialNumber}
? Notifications [BE-AP]: backend/notifications/{UserProfileUUID}
? Notification Resp [AP-BE]: apps/notifications/{UserProfileUUID}
? Devices Status [DE-BE]: devices/status/{SerialNumber}
? Apps Last-Will [AP-DE]: apps/lastwill/{ClientID}
? OTA Update [BE-DE]: backend/update/{SerialNumber} (has been changed to http)
? OTA Update Resp [DE-BE]: devices/update/{SerialNumber} (has been changed to http)

The Devices Status will be used to retain devices availability status. When a device connects to the broker it sends a retained “online” message and sends a retained “offline” message when either disconnecting gracefully or as a last-will message. The message is a ProtoBuf Info message which also contains the software version installed.
Debug commands
There are additional topics for development and debugging purposes available on machines that have not been set to production mode,

? For posting to channel: backend/debug/{SerialNumber}
? Output is passed back on: devices/console/{SerialNumber}
? Devices Settings [DE-AP]: devices/settings/{SerialNumber}

See Debug Messages Protocol for the debug commands specifications 
