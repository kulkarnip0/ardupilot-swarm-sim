#!/usr/bin/env python3

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "swarm.yaml"


WORLD_TEMPLATE = """<?xml version="1.0" ?>
<sdf version="1.9">
  <world name="{world_name}">
    <physics name="1ms" type="ignore">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>

    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
      <render_engine>ogre2</render_engine>
    </plugin>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu"/>
    <plugin filename="gz-sim-navsat-system" name="gz::sim::systems::NavSat"/>

    <scene>
      <ambient>1.0 1.0 1.0</ambient>
      <background>0.8 0.8 0.8</background>
      <sky/>
    </scene>

    <spherical_coordinates>
      <latitude_deg>-35.363262</latitude_deg>
      <longitude_deg>149.165237</longitude_deg>
      <elevation>584</elevation>
      <heading_deg>0</heading_deg>
      <surface_model>EARTH_WGS84</surface_model>
    </spherical_coordinates>

    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.8 0.8 0.8 1</diffuse>
      <specular>0.8 0.8 0.8 1</specular>
      <attenuation>
        <range>1000</range>
        <constant>0.9</constant>
        <linear>0.01</linear>
        <quadratic>0.001</quadratic>
      </attenuation>
      <direction>-0.5 0.1 -0.9</direction>
    </light>

    <include>
      <uri>model://runway</uri>
      <pose degrees="true">-29 545 0 0 0 363</pose>
    </include>

{uav_includes}
  </world>
</sdf>
"""


def get_mavutil():
    from pymavlink import mavutil

    return mavutil


def load_config(path: str):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r") as f:
        return yaml.safe_load(f)


def make_swarm_config(num_uavs: int):
    return {
        "project": {
            "name": "first_swarm_demo",
            "root": ".",
        },
        "world": {
            "name": "multi_iris_runway",
            "sdf": "worlds/multi_iris_runway.sdf",
        },
        "base_model": {
            "source": "/home/dev/ardupilot_gazebo/models/iris_with_gimbal",
        },
        "uavs": [
            {
                "id": uav_id,
                "name": f"iris_{uav_id}",
                "start_pose": [uav_id * 5, 0, 0.2, 0, 0, 0],
                "sitl_instance": uav_id,
                "mavlink_port": expected_mavlink_port(uav_id),
                "control_tcp_port": expected_control_tcp_port(uav_id),
                "fdm_port_in": expected_fdm_port_in(uav_id),
                "fdm_port_out": expected_fdm_port_out(uav_id),
            }
            for uav_id in range(num_uavs)
        ],
    }


def write_config(path: str, config):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.safe_dump(config, f, sort_keys=False)


def project_root_from_config(config_path: str, config):
    configured_root = Path(config.get("project", {}).get("root", "."))
    if configured_root.is_absolute():
        return configured_root
    return Path(config_path).resolve().parent / configured_root


def find_uav(config, uav_id: int):
    for uav in config.get("uavs", []):
        if int(uav["id"]) == int(uav_id):
            return uav
    raise RuntimeError(f"UAV id {uav_id} not found in swarm.yaml")


def expected_mavlink_port(instance: int):
    return 14550 + instance * 10


def expected_control_tcp_port(instance: int):
    return 5762 + instance * 10


def expected_fdm_port_in(instance: int):
    return 9002 + instance * 10


def expected_fdm_port_out(instance: int):
    return 9003 + instance * 10


def expected_system_id(uav):
    return int(uav["sitl_instance"]) + 1


def replace_xml_value(text: str, tag: str, value: int):
    pattern = rf"<{tag}>.*?</{tag}>"
    replacement = f"<{tag}>{value}</{tag}>"
    updated, count = re.subn(pattern, replacement, text)
    return updated, count


def replace_first_model_name(text: str, name: str):
    return re.sub(
        r"<model\s+name=\"[^\"]+\">",
        f"<model name=\"{name}\">",
        text,
        count=1,
    )


def replace_model_config_name(text: str, name: str):
    pattern = r"(<model>\s*<name>)(.*?)(</name>)"

    def replacement(match):
        return f"{match.group(1)}{name}{match.group(3)}"

    return re.sub(pattern, replacement, text, count=1, flags=re.DOTALL)


def patch_model_sdf(model_dir: Path, uav):
    model_sdf = model_dir / "model.sdf"
    if not model_sdf.exists():
        raise FileNotFoundError(f"Model SDF not found: {model_sdf}")

    text = model_sdf.read_text()
    text = replace_first_model_name(text, uav["name"])
    replacements = {
        "fdm_port_in": int(uav["fdm_port_in"]),
        "fdm_port_out": int(uav["fdm_port_out"]),
    }

    patched_any = False
    for tag, value in replacements.items():
        text, count = replace_xml_value(text, tag, value)
        patched_any = patched_any or count > 0

    if not patched_any:
        print(
            f"[swarmctl] WARNING: no fdm_port tags found in {model_sdf}; "
            "model may not connect to the requested SITL instance"
        )

    model_sdf.write_text(text)


def patch_model_config(model_dir: Path, name: str):
    model_config = model_dir / "model.config"
    if not model_config.exists():
        return

    text = model_config.read_text()
    text = replace_model_config_name(text, name)
    model_config.write_text(text)


def prepare_world_from_config(config_path: str, config):
    project_root = project_root_from_config(config_path, config)
    model_root = project_root / "models"
    world_path = project_root / config.get("world", {}).get(
        "sdf",
        "worlds/multi_iris_runway.sdf",
    )
    world_name = config.get("world", {}).get("name", world_path.stem)
    base_model = Path(config.get("base_model", {}).get("source", ""))

    if not base_model.exists():
        raise FileNotFoundError(
            f"Base model not found: {base_model}. "
            "Run this inside the Docker container after ardupilot_gazebo is installed."
        )

    model_root.mkdir(parents=True, exist_ok=True)
    world_path.parent.mkdir(parents=True, exist_ok=True)

    includes = []
    for uav in config.get("uavs", []):
        instance = int(uav["sitl_instance"])
        uav["fdm_port_in"] = int(uav.get("fdm_port_in", expected_fdm_port_in(instance)))
        uav["fdm_port_out"] = int(uav.get("fdm_port_out", expected_fdm_port_out(instance)))

        if uav["fdm_port_in"] != expected_fdm_port_in(instance):
            raise RuntimeError(
                f"{uav['name']} fdm_port_in={uav['fdm_port_in']} does not match "
                f"SITL instance {instance} default {expected_fdm_port_in(instance)}"
            )

        model_dir = model_root / uav["name"]
        if model_dir.exists():
            shutil.rmtree(model_dir)
        shutil.copytree(base_model, model_dir)
        patch_model_sdf(model_dir, uav)
        patch_model_config(model_dir, uav["name"])

        pose = " ".join(str(value) for value in uav.get("start_pose", [0, 0, 0.2, 0, 0, 0]))
        includes.append(
            f"""    <include>
      <name>{uav["name"]}</name>
      <pose>{pose}</pose>
      <uri>model://{uav["name"]}</uri>
    </include>"""
        )
        print(
            f"[swarmctl] Prepared {uav['name']}: "
            f"fdm_in={uav['fdm_port_in']}, fdm_out={uav['fdm_port_out']}"
        )

    world_path.write_text(
        WORLD_TEMPLATE.format(
            world_name=world_name,
            uav_includes="\n\n".join(includes),
        )
    )

    print(f"[swarmctl] Wrote world: {world_path}")
    print("[swarmctl] Run Gazebo with: swarmctl gazebo")


def prepare_world(args):
    config = load_config(args.config)
    prepare_world_from_config(args.config, config)


def create_swarm(args):
    config = make_swarm_config(args.num_uavs)
    write_config(args.config, config)
    print(f"[swarmctl] Wrote config: {args.config}")

    try:
        prepare_world_from_config(args.config, config)
    except FileNotFoundError as e:
        print(f"[swarmctl] WARNING: {e}")
        print("[swarmctl] World/model generation skipped. Run create inside Docker to generate Gazebo assets.")


def run_gazebo(args):
    config = load_config(args.config)
    project_root = project_root_from_config(args.config, config)
    model_root = project_root / "models"
    world_path = project_root / config.get("world", {}).get(
        "sdf",
        "worlds/multi_iris_runway.sdf",
    )

    if not world_path.exists():
        raise FileNotFoundError(
            f"World not found: {world_path}. Run swarmctl create --num-uavs N first."
        )

    env = dict(os.environ)
    resource_paths = [
        str(model_root),
        str(world_path.parent),
        env.get("GZ_SIM_RESOURCE_PATH", ""),
    ]
    env["GZ_SIM_RESOURCE_PATH"] = ":".join(path for path in resource_paths if path)
    env["GZ_PARTITION"] = env.get("GZ_PARTITION", "ardupilot_test")
    env["GZ_IP"] = env.get("GZ_IP", "127.0.0.1")
    env["GZ_TRANSPORT_IP"] = env.get("GZ_TRANSPORT_IP", "127.0.0.1")

    command = ["gz", "sim", "-v", "4"]
    if args.server:
        command.append("-s")
    if args.run:
        command.append("-r")
    command.append(str(world_path))

    print(f"[swarmctl] GZ_SIM_RESOURCE_PATH={env['GZ_SIM_RESOURCE_PATH']}")
    print(f"[swarmctl] Command: {' '.join(command)}")
    subprocess.run(command, env=env, check=True)


def start_uav(uav, launcher: str, background: bool = False):
    instance = int(uav["sitl_instance"])
    port = int(uav["mavlink_port"])
    command = [launcher, str(instance), str(port)]
    expected_port = expected_mavlink_port(instance)

    if port != expected_port:
        raise RuntimeError(
            f"{uav['name']} has mavlink_port={port}, but ArduPilot "
            f"SITL instance {instance} uses {expected_port} by default. "
            "Update swarm.yaml to match the instance, or update the launcher."
        )

    if not Path(launcher).exists():
        raise FileNotFoundError(
            f"SITL launcher not found: {launcher}. "
            "Run this inside the Docker container, or pass --launcher."
        )

    print(
        f"[swarmctl] Starting {uav['name']} "
        f"instance={instance}, mavlink_port={port}"
    )

    if background:
        log_path = Path("/tmp") / f"swarmctl_{uav['name']}.log"
        log = log_path.open("ab")
        proc = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log.close()
        print(f"[swarmctl] Started PID {proc.pid}, log={log_path}")
        return

    subprocess.run(command, check=True)


def start_swarm(config, background: bool = True):
    uavs = config.get("uavs", [])
    if not uavs:
        raise RuntimeError("No UAVs configured in swarm.yaml")

    ids = [int(uav["id"]) for uav in uavs]
    expected_ids = list(range(len(uavs)))
    if ids != expected_ids:
        raise RuntimeError(
            f"swarmctl start expects contiguous UAV ids {expected_ids}, got {ids}"
        )

    for uav in uavs:
        instance = int(uav["sitl_instance"])
        if int(uav["id"]) != instance:
            raise RuntimeError(
                f"{uav['name']} id={uav['id']} must match sitl_instance={instance} "
                "for multi-vehicle start"
            )
        if int(uav["mavlink_port"]) != expected_mavlink_port(instance):
            raise RuntimeError(
                f"{uav['name']} mavlink_port={uav['mavlink_port']} must be "
                f"{expected_mavlink_port(instance)} for instance {instance}"
            )

    run_dir = Path("/home/dev/sitl_gazebo_swarm")
    run_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "sim_vehicle.py",
        "-v",
        "ArduCopter",
        "-f",
        "gazebo-iris",
        "--model",
        "JSON",
        "--no-rebuild",
        "-I",
        "0",
        "--count",
        str(len(uavs)),
        "--auto-sysid",
    ]
    for uav in uavs:
        command.append(f"--out=udp:127.0.0.1:{int(uav['mavlink_port'])}")

    print(f"[swarmctl] Starting swarm with {len(uavs)} UAVs")
    print(f"[swarmctl] Command: {' '.join(command)}")

    if background:
        log_path = Path("/tmp/swarmctl_swarm.log")
        log = log_path.open("ab")
        proc = subprocess.Popen(
            command,
            cwd=run_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log.close()
        print(f"[swarmctl] Started PID {proc.pid}, log={log_path}")
        return

    subprocess.run(command, cwd=run_dir, check=True)


def stop_uav_processes(uav=None):
    patterns = []
    if uav is None:
        patterns = ["sim_vehicle.py", "arducopter", "mavproxy.py"]
        print("[swarmctl] Stopping all SITL/MAVProxy processes")
    else:
        instance = int(uav["sitl_instance"])
        mavlink_port = int(uav["mavlink_port"])
        sitl_tcp_port = 5760 + instance * 10
        patterns = [
            f"sim_vehicle.py.*-I {instance}",
            f"arducopter.*-I{instance}",
            f"mavproxy.py.*{mavlink_port}",
            f"mavproxy.py.*{sitl_tcp_port}",
        ]
        print(f"[swarmctl] Stopping {uav['name']}")

    for pattern in patterns:
        subprocess.run(["pkill", "-f", pattern], check=False)


def connect_to_uav(uav, timeout: int = 10):
    mavutil = get_mavutil()
    instance = int(uav["sitl_instance"])
    port = int(uav.get("control_tcp_port", expected_control_tcp_port(instance)))
    expected = expected_system_id(uav)
    conn_str = f"tcp:127.0.0.1:{port}"

    print(f"[swarmctl] Connecting to {uav['name']} on {conn_str}")
    master = mavutil.mavlink_connection(conn_str)

    print(f"[swarmctl] Waiting for HEARTBEAT from system {expected}...")
    start = time.time()
    heartbeat = None
    while time.time() - start < timeout:
        msg = master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if msg is None:
            continue
        if int(msg.get_srcSystem()) != expected:
            continue
        heartbeat = msg
        master.target_system = expected
        master.target_component = msg.get_srcComponent()
        break

    if heartbeat is None:
        raise TimeoutError(
            f"No HEARTBEAT received from {uav['name']} "
            f"system {expected} on {conn_str}"
        )
    master._swarmctl_heartbeat = heartbeat

    print(
        f"[swarmctl] Connected: "
        f"system={master.target_system}, "
        f"component={master.target_component}"
    )

    master.mav.request_data_stream_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL,
        2,
        1,
    )
    return master


def wait_ack(master, expected_command=None, timeout: int = 5):
    mavutil = get_mavutil()
    start = time.time()

    while time.time() - start < timeout:
        msg = master.recv_match(type="COMMAND_ACK", blocking=True, timeout=1)

        if msg is None:
            continue

        if expected_command is not None and msg.command != expected_command:
            continue

        result_name = mavutil.mavlink.enums["MAV_RESULT"][msg.result].name

        try:
            command_name = mavutil.mavlink.enums["MAV_CMD"][msg.command].name
        except Exception:
            command_name = str(msg.command)

        print(f"[swarmctl] ACK: {command_name} -> {result_name}")
        if msg.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
            raise RuntimeError(f"{command_name} failed: {result_name}")
        return msg

    raise TimeoutError("No COMMAND_ACK received")


def set_mode(master, mode_name: str):
    mavutil = get_mavutil()
    mode_name = mode_name.upper()
    mapping = master.mode_mapping()

    if mode_name not in mapping:
        available = ", ".join(mapping.keys())
        raise RuntimeError(f"Unknown mode '{mode_name}'. Available: {available}")

    mode_id = mapping[mode_name]

    print(f"[swarmctl] Setting mode: {mode_name}")

    master.mav.set_mode_send(
        master.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )

    time.sleep(1)


def arm(master, force: bool = False):
    mavutil = get_mavutil()
    print(f"[swarmctl] Sending ARM command, force={force}")

    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        1,                         # param1: 1 = arm
        21196 if force else 0,      # param2: ArduPilot force-arm magic value
        0, 0, 0, 0, 0,
    )

    wait_ack(
        master,
        expected_command=mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
    )


def disarm(master, force: bool = False):
    mavutil = get_mavutil()
    print(f"[swarmctl] Sending DISARM command, force={force}")

    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        0,                         # param1: 0 = disarm
        21196 if force else 0,      # param2: ArduPilot force-disarm magic value
        0, 0, 0, 0, 0,
    )

    wait_ack(
        master,
        expected_command=mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
    )


def rc_override(master, channel: int, pwm: int, verbose: bool = True):
    if not 1 <= channel <= 18:
        raise ValueError("RC channel must be between 1 and 18")

    if verbose:
        print(f"[swarmctl] RC override: channel={channel}, pwm={pwm}")

    values = [65535] * 18
    values[channel - 1] = pwm

    master.mav.rc_channels_override_send(
        master.target_system,
        master.target_component,
        *values,
    )


def rc_override_for(master, channel: int, pwm: int, duration: float = 3.0, rate: float = 10.0):
    if duration <= 0:
        rc_override(master, channel, pwm)
        return

    print(
        f"[swarmctl] Holding RC override: "
        f"channel={channel}, pwm={pwm}, duration={duration:.1f}s"
    )
    end = time.time() + duration
    interval = 1.0 / rate

    while time.time() < end:
        rc_override(master, channel, pwm, verbose=False)
        time.sleep(interval)

    print("[swarmctl] RC override complete")


def rc_override_for_many(items, channel: int, pwm: int, duration: float = 3.0, rate: float = 10.0):
    if duration <= 0:
        for uav, master in items:
            print(f"[swarmctl] {uav['name']}: RC override channel={channel}, pwm={pwm}")
            rc_override(master, channel, pwm, verbose=False)
        return

    names = ", ".join(uav["name"] for uav, _ in items)
    print(
        f"[swarmctl] Holding RC override for {names}: "
        f"channel={channel}, pwm={pwm}, duration={duration:.1f}s"
    )
    end = time.time() + duration
    interval = 1.0 / rate

    while time.time() < end:
        for _, master in items:
            rc_override(master, channel, pwm, verbose=False)
        time.sleep(interval)

    print("[swarmctl] RC override complete")


def throttle(master, pwm: int, duration: float = 3.0):
    # ArduCopter throttle is RC channel 3.
    rc_override_for(master, channel=3, pwm=pwm, duration=duration)


def run_rc_for_selected(args, channel: int, pwm: int, duration: float):
    config = load_config(args.config)
    selected = selected_uavs(config, args)
    items = []

    for uav in selected:
        print(f"[swarmctl] === {uav['name']} ===")
        items.append((uav, connect_to_uav(uav)))

    rc_override_for_many(items, channel, pwm, duration=duration)


def land(master):
    print("[swarmctl] LAND")
    set_mode(master, "LAND")


def param_set(master, name: str, value: float, required: bool = True):
    mavutil = get_mavutil()
    print(f"[swarmctl] Setting param {name} = {value}")

    master.mav.param_set_send(
        master.target_system,
        master.target_component,
        name.encode("utf-8"),
        float(value),
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
    )

    msg = wait_param_value(master, name, timeout=5)
    if msg is not None:
        print(f"[swarmctl] PARAM_VALUE: {name} = {msg.param_value}")
        return msg

    print(f"[swarmctl] No immediate confirmation for {name}; requesting value")

    master.mav.param_request_read_send(
        master.target_system,
        master.target_component,
        name.encode("utf-8"),
        -1,
    )

    msg = wait_param_value(master, name, timeout=5)
    if msg is None:
        if not required:
            print(f"[swarmctl] WARNING: no PARAM_VALUE confirmation for {name}")
            return None
        raise TimeoutError(f"No PARAM_VALUE confirmation received for {name}")

    print(f"[swarmctl] PARAM_VALUE: {name} = {msg.param_value}")
    return msg


def wait_param_value(master, name: str, timeout: int = 5):
    start = time.time()
    while time.time() - start < timeout:
        msg = master.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
        if msg is None:
            continue

        param_id = msg.param_id
        if isinstance(param_id, bytes):
            param_id = param_id.decode("utf-8", errors="ignore")

        param_id = param_id.strip("\x00")

        if param_id == name:
            return msg

    return None


def status(master):
    mavutil = get_mavutil()
    print("[swarmctl] Reading status...")

    hb = getattr(master, "_swarmctl_heartbeat", None)
    if hb is None:
        hb = master.recv_match(type="HEARTBEAT", blocking=True, timeout=5)
    if hb:
        mode = mavutil.mode_string_v10(hb)
        armed = bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        print(f"Mode:  {mode}")
        print(f"Armed: {armed}")

    pos = master.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=1)
    if pos:
        print(f"Relative altitude: {pos.relative_alt / 1000.0:.2f} m")
        print(f"MSL altitude:      {pos.alt / 1000.0:.2f} m")

    hud = master.recv_match(type="VFR_HUD", blocking=True, timeout=1)
    if hud:
        print(f"Groundspeed: {hud.groundspeed:.2f} m/s")
        print(f"Climb rate:  {hud.climb:.2f} m/s")
        print(f"Heading:     {hud.heading} deg")
        print(f"Throttle:    {hud.throttle} %")


def configure_sim(master):
    print("[swarmctl] Configuring simulation params")
    param_set(master, "FRAME_CLASS", 1)
    param_set(master, "FRAME_TYPE", 1)
    param_set(master, "ARMING_CHECK", 0, required=False)
    print("[swarmctl] Frame params may require restarting SITL before arming")


def run_for_uav(args, fn):
    config = load_config(args.config)
    uav = find_uav(config, args.uav)
    master = connect_to_uav(uav)
    fn(master)


def selected_uavs(config, args):
    if getattr(args, "all", False):
        return config.get("uavs", [])
    if getattr(args, "uav", None) is not None:
        return [find_uav(config, args.uav)]
    raise RuntimeError("Specify --uav ID or --all")


def run_for_selected(args, fn):
    config = load_config(args.config)
    for uav in selected_uavs(config, args):
        print(f"[swarmctl] === {uav['name']} ===")
        master = connect_to_uav(uav)
        fn(master)


def run_start(args):
    config = load_config(args.config)
    if args.uav is None:
        start_swarm(config, background=not args.foreground)
        return

    uav = find_uav(config, args.uav)
    start_uav(uav, args.launcher, background=args.background)


def run_stop(args):
    config = load_config(args.config)
    if args.uav is None:
        stop_uav_processes()
        return

    stop_uav_processes(find_uav(config, args.uav))


def main():
    parser = argparse.ArgumentParser(
        description="Small swarm control CLI for ArduPilot SITL"
    )

    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help=f"Path to swarm.yaml. Default: {DEFAULT_CONFIG}",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create")
    p.add_argument("--num-uavs", type=int, required=True)

    sub.add_parser("prepare-world")

    p = sub.add_parser("gazebo")
    p.add_argument("--server", action="store_true", help="Run Gazebo server only")
    p.add_argument(
        "--paused",
        action="store_true",
        help="Start Gazebo paused instead of running immediately",
    )
    p.set_defaults(run=True)

    p = sub.add_parser("start")
    p.add_argument("--uav", type=int)
    p.add_argument(
        "--launcher",
        default="/home/dev/run_sitl_gazebo_instance.sh",
        help="Path to SITL launcher script",
    )
    p.add_argument("--background", action="store_true")
    p.add_argument(
        "--foreground",
        action="store_true",
        help="Keep swarm start attached to this terminal",
    )

    p = sub.add_parser("status")
    p.add_argument("--uav", type=int)
    p.add_argument("--all", action="store_true")

    p = sub.add_parser("configure")
    p.add_argument("--uav", type=int)
    p.add_argument("--all", action="store_true")

    p = sub.add_parser("mode")
    p.add_argument("--uav", type=int)
    p.add_argument("--all", action="store_true")
    p.add_argument("mode_name")

    p = sub.add_parser("arm")
    p.add_argument("--uav", type=int)
    p.add_argument("--all", action="store_true")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("disarm")
    p.add_argument("--uav", type=int)
    p.add_argument("--all", action="store_true")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("throttle")
    p.add_argument("--uav", type=int)
    p.add_argument("--all", action="store_true")
    p.add_argument("--duration", type=float, default=3.0)
    p.add_argument("pwm", type=int)

    p = sub.add_parser("rc")
    p.add_argument("--uav", type=int)
    p.add_argument("--all", action="store_true")
    p.add_argument("--duration", type=float, default=3.0)
    p.add_argument("channel", type=int)
    p.add_argument("pwm", type=int)

    p = sub.add_parser("land")
    p.add_argument("--uav", type=int)
    p.add_argument("--all", action="store_true")

    p = sub.add_parser("stop")
    p.add_argument("--uav", type=int)

    p = sub.add_parser("param-set")
    p.add_argument("--uav", type=int, required=True)
    p.add_argument("name")
    p.add_argument("value", type=float)

    args = parser.parse_args()

    try:
        if args.cmd == "create":
            create_swarm(args)

        elif args.cmd == "prepare-world":
            prepare_world(args)

        elif args.cmd == "gazebo":
            args.run = not args.paused
            run_gazebo(args)

        elif args.cmd == "start":
            run_start(args)

        elif args.cmd == "status":
            run_for_selected(args, status)

        elif args.cmd == "configure":
            run_for_selected(args, configure_sim)

        elif args.cmd == "mode":
            run_for_selected(args, lambda master: set_mode(master, args.mode_name))

        elif args.cmd == "arm":
            run_for_selected(args, lambda master: arm(master, force=args.force))

        elif args.cmd == "disarm":
            run_for_selected(args, lambda master: disarm(master, force=args.force))

        elif args.cmd == "throttle":
            run_rc_for_selected(args, channel=3, pwm=args.pwm, duration=args.duration)

        elif args.cmd == "rc":
            run_rc_for_selected(
                args,
                channel=args.channel,
                pwm=args.pwm,
                duration=args.duration,
            )

        elif args.cmd == "land":
            run_for_selected(args, land)

        elif args.cmd == "stop":
            run_stop(args)

        elif args.cmd == "param-set":
            run_for_uav(args, lambda master: param_set(master, args.name, args.value))

    except Exception as e:
        print(f"[swarmctl] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
