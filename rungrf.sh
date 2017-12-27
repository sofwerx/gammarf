#!/bin/bash

./reset_hackrf.sh
docker run -it --net="host" --privileged gammarf
