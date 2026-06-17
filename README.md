# ArduPilot Swarm Simulator

ArduPilot Swarm Simulator is a Docker-backed Gazebo Harmonic and ArduPilot SITL workspace for running a small multi-Iris UAV swarm on a shared runway world.

The project contains:

- a generated Gazebo world with three Iris UAV instances
- per-UAV model copies with separate FDM ports
- a YAML swarm configuration
- a `swarmctl` command-line tool for world generation, SITL startup, status checks, arming, mode changes, RC overrides, landing, and cleanup
- Docker build/run scripts for a repeatable Ubuntu ROS Humble, Gazebo Harmonic, ArduPilot, and `ardupilot_gazebo` environment

## Repository Layout

```text
.
├── README.md
└── swarm_sim
    ├── .gitignore
    ├── docker
    │   ├── Dockerfile.harmonic
    │   ├── build_docker.sh
    │   └── run_docker.sh
    ├── models
    │   ├── iris_0
    │   ├── iris_1
    │   └── iris_2
    ├── scripts
    │   └── swarmctl.py
    ├── swarm.yaml
    └── worlds
        └── multi_iris_runway.sdf
```

## What It Runs

The default swarm contains three Iris UAVs:

| UAV | SITL instance | MAVLink UDP out | Control TCP | FDM in | FDM out | Start pose |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `iris_0` | `0` | `14550` | `5762` | `9002` | `9003` | `0 0 0.2 0 0 0` |
| `iris_1` | `1` | `14560` | `5772` | `9012` | `9013` | `5 0 0.2 0 0 0` |
| `iris_2` | `2` | `14570` | `5782` | `9022` | `9023` | `10 0 0.2 0 0 0` |

The generated world is `swarm_sim/worlds/multi_iris_runway.sdf`. It includes the ArduPilot Gazebo runway model and three UAV model includes.

## Requirements

Host requirements:

- Linux host with Docker
- X11 display access if you want the Gazebo GUI
- Enough disk space and time for the Docker image build, because it clones and builds ArduPilot and `ardupilot_gazebo`

Inside the Docker image:

- Ubuntu/ROS Humble base
- Gazebo Harmonic
- ArduPilot SITL
- `ardupilot_gazebo`
- MAVProxy
- `pymavlink`
- `pyyaml`

## Build The Docker Image

From the repository root:

```bash
cd swarm_sim/docker
./build_docker.sh
```

The image is tagged:

```text
ardupilot-sim-harmonic
```

The build script passes host proxy variables through to Docker and uses host networking during the build.

## Start The Container

From the repository root:

```bash
cd swarm_sim/docker
./run_docker.sh
```

The script mounts the workspace at:

```text
/workspace
```

The container provides a `swarmctl` command on `PATH`, which calls:

```text
/workspace/swarm_sim/scripts/swarmctl.py
```

You can verify the mount from inside the container:

```bash
check_swarm_mount.sh
```

## Generate Or Regenerate A Swarm

Inside the container:

```bash
cd /workspace
swarmctl create --num-uavs 3
```

This writes `swarm_sim/swarm.yaml`, copies the base Iris Gazebo model from:

```text
/home/dev/ardupilot_gazebo/models/iris_with_gimbal
```

and generates:

- `swarm_sim/models/iris_0`
- `swarm_sim/models/iris_1`
- `swarm_sim/models/iris_2`
- `swarm_sim/worlds/multi_iris_runway.sdf`

If `swarm.yaml` already exists and you only want to regenerate the world and model copies:

```bash
swarmctl prepare-world
```

## Run Gazebo

Inside the container:

```bash
cd /workspace
swarmctl gazebo
```

To start paused:

```bash
swarmctl gazebo --paused
```

To run the Gazebo server only:

```bash
swarmctl gazebo --server
```

The Docker image also includes:

```bash
run_gazebo_swarm.sh
```

## Start ArduPilot SITL

Start the full configured swarm:

```bash
swarmctl start
```

Keep SITL attached to the terminal:

```bash
swarmctl start --foreground
```

Start one UAV instance:

```bash
swarmctl start --uav 0 --background
```

The default launcher is:

```text
/home/dev/run_sitl_gazebo_instance.sh
```

The full-swarm startup uses `sim_vehicle.py` with:

```text
ArduCopter gazebo-iris JSON --count N --auto-sysid
```

## Basic Control Commands

Check one UAV:

```bash
swarmctl status --uav 0
```

Check all UAVs:

```bash
swarmctl status --all
```

Configure common simulation parameters:

```bash
swarmctl configure --all
```

Set mode:

```bash
swarmctl mode --uav 0 GUIDED
swarmctl mode --all LAND
```

Arm:

```bash
swarmctl arm --uav 0
swarmctl arm --all --force
```

Disarm:

```bash
swarmctl disarm --uav 0
swarmctl disarm --all --force
```

Land:

```bash
swarmctl land --all
```

Send throttle override on RC channel 3:

```bash
swarmctl throttle --uav 0 1600 --duration 3
swarmctl throttle --all 1500 --duration 2
```

Send any RC override:

```bash
swarmctl rc --uav 1 1 1600 --duration 2
swarmctl rc --all 4 1400 --duration 2
```

Set an ArduPilot parameter:

```bash
swarmctl param-set --uav 0 ARMING_CHECK 0
```

Stop SITL/MAVProxy processes:

```bash
swarmctl stop
```

Stop one UAV:

```bash
swarmctl stop --uav 1
```

## Typical Workflow

Use separate terminals inside the container:

Terminal 1:

```bash
cd /workspace
swarmctl prepare-world
swarmctl gazebo
```

Terminal 2:

```bash
cd /workspace
swarmctl start --foreground
```

Terminal 3:

```bash
cd /workspace
swarmctl status --all
swarmctl configure --all
swarmctl mode --all GUIDED
swarmctl arm --all --force
```

## Configuration

The main config file is:

```text
swarm_sim/swarm.yaml
```

Important fields:

- `project.root`: project root relative to the config file
- `world.sdf`: generated world path
- `base_model.source`: source Gazebo model copied per UAV
- `uavs`: list of UAV definitions

For multi-vehicle startup, UAV IDs must be contiguous and must match `sitl_instance`. The default port scheme is:

- MAVLink UDP out: `14550 + instance * 10`
- control TCP: `5762 + instance * 10`
- FDM in: `9002 + instance * 10`
- FDM out: `9003 + instance * 10`

## Troubleshooting

If Gazebo cannot find models, confirm `GZ_SIM_RESOURCE_PATH` includes:

```text
/workspace/swarm_sim/models
/workspace/swarm_sim/worlds
/home/dev/ardupilot_gazebo/models
/home/dev/ardupilot_gazebo/worlds
```

If `swarmctl prepare-world` fails with a missing base model, run it inside the Docker container after the image has built `ardupilot_gazebo`.

If `swarmctl status`, `arm`, or `mode` cannot connect, make sure the matching SITL instance is running and that the control TCP port in `swarm.yaml` matches the SITL instance.

If arming fails, run:

```bash
swarmctl configure --all
```

then restart SITL and try arming again.

## Notes

This is a simulation project intended for local development and experimentation. Review all vehicle configuration and safety behavior before adapting any part of it to real hardware.
