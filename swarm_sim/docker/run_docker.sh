xhost +local:docker
docker run -it --rm \
  --name ardupilot-sim-harmonic \
  --network=host \
  --hostname ardupilot-sim-harmonic \
  -e DISPLAY=$DISPLAY \
  -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v /home/praveen/workspace/shatriya:/workspace \
  ardupilot-sim-harmonic