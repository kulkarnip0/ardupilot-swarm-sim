FROM osrf/ros:humble-desktop
ENV NVIDIA_VISIBLE_DEVICES ${NVIDIA_VISIBLE_DEVICES:-all}
ENV NVIDIA_DRIVER_CAPABILITIES ${NVIDIA_DRIVER_CAPABILITIES:+$NVIDIA_DRIVER_CAPABILITIES,}graphics,compute,utility

ARG DEBIAN_FRONTEND=noninteractive

ARG http_proxy
ARG https_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY

ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}
ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}

# Gazebo transport settings needed inside Docker
ENV GZ_PARTITION=ardupilot_test
ENV GZ_IP=127.0.0.1
ENV GZ_TRANSPORT_IP=127.0.0.1

# Basic system setup
RUN apt-get update && apt-get install -y \
    sudo \
    git \
    curl \
    wget \
    gnupg \
    lsb-release \
    ca-certificates \
    software-properties-common \
    build-essential \
    cmake \
    pkg-config \
    python3 \
    python3-pip \
    python3-dev \
    python3-setuptools \
    python3-wheel \
    python3-colcon-common-extensions \
    python3-venv \
    nano \
    vim \
    tmux \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Add Gazebo Harmonic repository
RUN curl -sSL https://packages.osrfoundation.org/gazebo.gpg \
    -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
    http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/gazebo-stable.list

# Install Gazebo Harmonic
RUN apt-get update && apt-get install -y \
    gz-harmonic \
    && rm -rf /var/lib/apt/lists/*

# ROS-Gazebo useful packages
RUN apt-get update && apt-get install -y \
    ros-humble-ros-gz \
    ros-humble-ros-gz-bridge \
    ros-humble-ros-gz-sim \
    ros-humble-xacro \
    ros-humble-tf2-ros \
    ros-humble-rviz2 \
    && rm -rf /var/lib/apt/lists/*

# Dependencies for ArduPilot and ardupilot_gazebo
RUN apt-get update && apt-get install -y \
    gawk \
    ccache \
    g++ \
    gdb \
    make \
    ninja-build \
    rsync \
    unzip \
    libtool \
    libxml2-dev \
    libxslt1-dev \
    python3-lxml \
    python3-future \
    python3-matplotlib \
    python3-opencv \
    python3-yaml \
    python3-empy \
    python3-numpy \
    python3-pexpect \
    python3-jinja2 \
    python3-serial \
    python3-scipy \
    python3-testresources \
    rapidjson-dev \
    libopencv-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    gstreamer1.0-gl \
    && rm -rf /var/lib/apt/lists/*

# RapidJSON CMake config fallback
RUN mkdir -p /usr/lib/cmake/RapidJSON && \
    cat > /usr/lib/cmake/RapidJSON/RapidJSONConfig.cmake <<'EOF'
set(RapidJSON_FOUND TRUE)
set(RapidJSON_INCLUDE_DIRS "/usr/include")

if(NOT TARGET RapidJSON::RapidJSON)
  add_library(RapidJSON::RapidJSON INTERFACE IMPORTED)
  set_target_properties(RapidJSON::RapidJSON PROPERTIES
    INTERFACE_INCLUDE_DIRECTORIES "/usr/include")
endif()
EOF

# Create non-root user
RUN useradd -ms /bin/bash dev && \
    echo "dev ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER dev
WORKDIR /home/dev

# Python user local bin
ENV PATH="/home/dev/.local/bin:${PATH}"

# Install MAVProxy and Python MAVLink tools
RUN python3 -m pip install --user --upgrade pip setuptools wheel && \
    python3 -m pip install --user \
    MAVProxy \
    pymavlink \
    pyyaml

# Clone ArduPilot
RUN git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git /home/dev/ardupilot

WORKDIR /home/dev/ardupilot

# Build ArduCopter SITL
RUN ./waf configure --board sitl && \
    ./waf copter

# Clone ArduPilot Gazebo plugin
WORKDIR /home/dev

RUN git clone https://github.com/ArduPilot/ardupilot_gazebo.git /home/dev/ardupilot_gazebo

# Build ArduPilot Gazebo plugin
WORKDIR /home/dev/ardupilot_gazebo

RUN mkdir -p build && cd build && \
    cmake .. \
      -DCMAKE_BUILD_TYPE=RelWithDebInfo \
      -DRapidJSON_DIR=/usr/lib/cmake/RapidJSON && \
    make -j$(nproc)

# Environment setup
RUN echo 'source /opt/ros/humble/setup.bash' >> /home/dev/.bashrc && \
    echo 'export PATH=$PATH:/home/dev/ardupilot/Tools/autotest' >> /home/dev/.bashrc && \
    echo 'export PATH=$PATH:/home/dev/.local/bin' >> /home/dev/.bashrc && \
    echo 'export GZ_PARTITION=ardupilot_test' >> /home/dev/.bashrc && \
    echo 'export GZ_IP=127.0.0.1' >> /home/dev/.bashrc && \
    echo 'export GZ_TRANSPORT_IP=127.0.0.1' >> /home/dev/.bashrc && \
    echo 'export GZ_SIM_SYSTEM_PLUGIN_PATH=$GZ_SIM_SYSTEM_PLUGIN_PATH:/home/dev/ardupilot_gazebo/build' >> /home/dev/.bashrc && \
    echo 'export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:/home/dev/ardupilot_gazebo/models:/home/dev/ardupilot_gazebo/worlds:/workspace/swarm_sim/models:/workspace/swarm_sim/worlds' >> /home/dev/.bashrc

# Convenience script: run Gazebo Iris world
RUN cat > /home/dev/run_gazebo_iris.sh <<'EOF'
#!/bin/bash
set -e

source ~/.bashrc

export GZ_PARTITION=ardupilot_test
export GZ_IP=127.0.0.1
export GZ_TRANSPORT_IP=127.0.0.1
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:/workspace/swarm_sim/models:/workspace/swarm_sim/worlds

pkill -f "gz sim" || true

echo "Starting Gazebo Harmonic Iris runway world..."
gz sim -v 4 -s -r /home/dev/ardupilot_gazebo/worlds/iris_runway.sdf
EOF

RUN chmod +x /home/dev/run_gazebo_iris.sh

# Convenience script: run generated multi-Iris swarm world
RUN cat > /home/dev/run_gazebo_swarm.sh <<'EOF'
#!/bin/bash
set -e

source ~/.bashrc

export GZ_PARTITION=ardupilot_test
export GZ_IP=127.0.0.1
export GZ_TRANSPORT_IP=127.0.0.1
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:/workspace/swarm_sim/models:/workspace/swarm_sim/worlds

pkill -f "gz sim" || true

if [ ! -f /workspace/swarm_sim/worlds/multi_iris_runway.sdf ]; then
  echo "ERROR: /workspace/swarm_sim/worlds/multi_iris_runway.sdf not found."
  echo "Run: swarmctl prepare-world"
  exit 1
fi

echo "Starting Gazebo Harmonic multi-Iris swarm world..."
gz sim -v 4 -r /workspace/swarm_sim/worlds/multi_iris_runway.sdf
EOF

RUN chmod +x /home/dev/run_gazebo_swarm.sh

# Convenience script: run ArduPilot SITL connected to Gazebo
RUN cat > /home/dev/run_sitl_gazebo_instance.sh <<'EOF'
#!/bin/bash
set -e

source ~/.bashrc

INSTANCE="${1:-0}"
MAVLINK_PORT="${2:-14550}"

export GZ_PARTITION=ardupilot_test
export GZ_IP=127.0.0.1
export GZ_TRANSPORT_IP=127.0.0.1

mkdir -p "/home/dev/sitl_gazebo_run_${INSTANCE}"
cd "/home/dev/sitl_gazebo_run_${INSTANCE}"

echo "Starting ArduPilot SITL instance ${INSTANCE} connected to Gazebo..."
echo "Expected default MAVLink output: 127.0.0.1:${MAVLINK_PORT}"
sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --no-rebuild \
  -I "${INSTANCE}"
EOF

RUN chmod +x /home/dev/run_sitl_gazebo_instance.sh && \
    cat > /home/dev/run_sitl_gazebo.sh <<'EOF'
#!/bin/bash
exec /home/dev/run_sitl_gazebo_instance.sh 0 14550
EOF

RUN chmod +x /home/dev/run_sitl_gazebo.sh && \
    cat > /home/dev/run_sitl_gazebo_uav0.sh <<'EOF'
#!/bin/bash
exec /home/dev/run_sitl_gazebo_instance.sh 0 14550
EOF

RUN chmod +x /home/dev/run_sitl_gazebo_uav0.sh && \
    cat > /home/dev/run_sitl_gazebo_uav1.sh <<'EOF'
#!/bin/bash
exec /home/dev/run_sitl_gazebo_instance.sh 1 14560
EOF

RUN chmod +x /home/dev/run_sitl_gazebo_uav1.sh

# Convenience script: monitor Iris pose
RUN cat > /home/dev/monitor_iris_pose.sh <<'EOF'
#!/bin/bash
set -e

source ~/.bashrc

gz topic -e -t /world/iris_runway/pose/info | \
grep -A8 -B2 'name: "iris_with_gimbal"'
EOF

RUN chmod +x /home/dev/monitor_iris_pose.sh

# Host-mounted swarm_sim support
ENV PATH="/home/dev/.local/bin:${PATH}"

RUN mkdir -p /home/dev/.local/bin && \
    cat > /home/dev/.local/bin/swarmctl <<'EOF'
#!/bin/bash
python3 /workspace/swarm_sim/scripts/swarmctl.py "$@"
EOF

RUN chmod +x /home/dev/.local/bin/swarmctl && \
    echo 'export PATH=$HOME/.local/bin:$PATH' >> /home/dev/.bashrc

RUN cat > /home/dev/check_swarm_mount.sh <<'EOF'
#!/bin/bash

if [ ! -f /workspace/swarm_sim/scripts/swarmctl.py ]; then
  echo "ERROR: /workspace/swarm_sim/scripts/swarmctl.py not found."
  echo "Did you mount the workspace root to /workspace?"
  echo ""
  echo "Expected:"
  echo '  /workspace should contain swarm_sim/scripts/swarmctl.py'
  exit 1
fi

echo "swarm_sim mount OK:"
ls -l /workspace/swarm_sim
EOF

RUN chmod +x /home/dev/check_swarm_mount.sh

WORKDIR /workspace

CMD ["/bin/bash"]
