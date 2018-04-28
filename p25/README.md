
Using ΓRF for P25 Digital Trunking
======================================

* In the ΓRF client, run the p25log module on a pseudo-device (type `mods`
if you're unsure about syntax.)  This will tell the client to accept
`trunk-recorder` log output on a UDP port, process it, and send it to the
server.

* Get `trunk-recorder` from [here](https://github.com/robotastic/trunk-recorder).
Tested to work with trunk-recorder version 3.0.1

* Configure.  Don't configure any analog or digital recorders (value should be '0')

* Build `trunk-recorder`: `# docker build .`  Make note of the ID given at the
end of the Docker output.

* Run:
`# docker run -d -it --net="host" --privileged -v /dev/bus/usb:/dev/bus/usb [ID] /bin/sh -c 'cd /src/trunk-recorder ; ./recorder'`

* Get the process ID: `# docker ps`

* start the p25log module in the grf client: `run p25log 9000 50000`  (it will listen on port 50000, here)

* Forward the logs: `# docker logs --tail 1 -f [PID] | nc -u 127.0.0.1 50000`
