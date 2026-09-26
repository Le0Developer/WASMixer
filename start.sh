#!/bin/bash

# Start SSH when the container is used for remote access.
ssh-keygen -A
mkdir -p /run/sshd
/usr/sbin/sshd

exec /bin/bash
# docker run -it wasmaker
