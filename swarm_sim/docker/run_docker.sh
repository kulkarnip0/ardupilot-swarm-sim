xhost +local:docker
xhost +local:root

docker run -it --rm \
  --name ardupilot-sim-harmonic \
  --network=host \
  --hostname ardupilot-sim-harmonic \
  --gpus all \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
  -e QT_X11_NO_MITSHM=1 \
  -v /home/praveen/workspace/shatriya:/workspace \
  ardupilot-sim-harmonic