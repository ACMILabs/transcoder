#!/bin/bash

# This loop is a way of waiting for Docker to finish launching.
while true
do
cd ~/transcoder/ && docker compose -f docker-compose-dev.yml up --build >> ~/transcoder_log.txt
done
