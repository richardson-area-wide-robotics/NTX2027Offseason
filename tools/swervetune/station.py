"""The Driver Station laptop, its firewall, and the robot's radio: what keeps a robot from connecting.

``tools/robot_preflight.ps1 -Json`` reads the facts on the laptop (it changes nothing): the Driver
Station's version and team number, each adapter's address, the firewall, and which radios answer.
This turns them into checks, the same shape as the script's own (``id``, ``level``, ``title``,
``why``), each with a ``group`` so the page can show them under headings.

What the checks rely on, from WPILib's networking pages and Vivid-Hosting's VH-109 radio docs
(read October 2026):

* Addresses: the robot radio is 10.TE.AM.1, the robot 10.TE.AM.2, the access point radio at home
  10.TE.AM.4. A radio hands out 10.TE.AM.200 to .219; the field hands the Driver Station .20 to .199.
  A static Driver Station is 10.TE.AM.5 with mask 255.0.0.0 (or 255.255.255.0 with gateway
  10.TE.AM.4); never .1 to .4 or .20 and up. TE.AM splits the team number: 17451 is 10.174.51.
* A radio out of the box is team 1 (10.0.1.1). Its setup address is 192.168.69.1, wired to its DS
  port with the laptop at 192.168.69.2; also http://radio.local/.
* At events a kiosk programs the robot radio; at home it must match the access point radio's mode,
  team number, suffix and WPA keys, or it never links. Its SYS light blinking once a second means it
  can't reach 10.TE.AM.4. A page that shows no firmware version means firmware before 1.2.0; events
  have required 1.3.0 or newer since 2025.
* The Driver Station's year matches the robot code's (2026 Game Tools, Driver Station 26.x), and its
  team number is the robot's.
"""

from __future__ import annotations

import glob
import os
import re

DS = "Driver Station"
ADDRESS = "This laptop on the robot's network"
FIREWALL = "Firewall"
RADIO = "Radio and robot"
INTERNET = "Internet and Claude"
ROBOT = "The robot's software"

# The network script's own checks, by id, under the same headings.
SCRIPT_GROUPS = {"internet": INTERNET, "vpn": INTERNET, "claude": INTERNET, "claude-route": INTERNET,
                 "killswitch": INTERNET, "robot-adapter": ADDRESS, "robot-route": ADDRESS, "robot-metric": ADDRESS,
                 "overlap": ADDRESS, "robot-ping": RADIO, "nt4": RADIO, "firewall": FIREWALL}
ORDER = [DS, ADDRESS, FIREWALL, RADIO, ROBOT, INTERNET]
MIN_FIRMWARE = (1, 3, 0)


def _check(cid, group, level, title, why):
    return {"id": cid, "group": group, "level": level, "title": title, "why": why}


def subnet(team):
    te, am = divmod(int(team), 100)
    return f"10.{te}.{am}"


def team_of(ip):
    """The team a 10.TE.AM.x address belongs to, or None."""
    m = re.fullmatch(r"10\.(\d+)\.(\d+)\.\d+", str(ip or ""))
    return int(m.group(1)) * 100 + int(m.group(2)) if m and int(m.group(2)) < 100 else None


# ---------------------------------------------------------------------------- the Driver Station
def driver_station(ds, team, year):
    ds = ds or {}
    out = []
    if not ds.get("installed"):
        return [_check("ds-installed", DS, "warn", "No Driver Station on this laptop",
                       f"Install FRC Game Tools {year or ''} (it has the Driver Station) on the laptop that drives "
                       "the robot. Skip this if another laptop is the Driver Station.".replace("  ", " "))]
    ver = str(ds.get("version") or "")
    major = int(ver.split(".")[0]) if ver.split(".")[0].isdigit() else None
    want = int(year) % 100 if year else None
    if major is None or want is None:
        out.append(_check("ds-version", DS, "info", f"Driver Station {ver or '(version unknown)'}",
                          "Its year must match the robot code's."))
    elif major == want:
        out.append(_check("ds-version", DS, "ok", f"Driver Station {ver}, for {year}", "The same year as the robot code."))
    else:
        out.append(_check("ds-version", DS, "fail", f"Driver Station 20{major:02d}, but the robot code is {year}",
                          f"A Driver Station from another year can't run this robot. Install FRC Game Tools {year}, "
                          "then the latest update for it."))
    if not ds.get("ini"):
        out.append(_check("ds-team", DS, "warn", "The Driver Station hasn't been set up on this laptop",
                          f"Open it once and set Team Number to {team} (the Setup tab, the gear)."))
    elif ds.get("team") is None:
        keys = ", ".join(k for k in ds.get("ini_keys") or [] if "team" in str(k).lower()) or "none with 'team' in the name"
        out.append(_check("ds-team", DS, "warn", "The Driver Station's team number couldn't be read",
                          f"Check it says {team} (the Setup tab, the gear). Its settings file's team entries: {keys}."))
    elif int(ds["team"]) != int(team):
        out.append(_check("ds-team", DS, "fail", f"The Driver Station is set to team {ds['team']}; this robot is {team}",
                          f"It looks for the robot at {subnet(ds['team'])}.2. Set Team Number to {team} (the Setup "
                          "tab, the gear)."))
    else:
        out.append(_check("ds-team", DS, "ok", f"The Driver Station is set to team {team}", "It looks for this robot."))
    return out


# ---------------------------------------------------------------------------- this laptop's address
def addresses(adapters, team, internet_adapter=""):
    """Each adapter that is, or looks like it should be, on a robot's network."""
    out = []
    ours = subnet(team)
    for a in adapters or []:
        name, ip, prefix = a.get("name", "?"), str(a.get("ip") or ""), int(a.get("prefix") or 0)
        dhcp, gw = bool(a.get("dhcp")), str(a.get("gateway") or "")
        if name == internet_adapter and not a.get("robot"):
            continue
        if ip.startswith("169.254."):
            out.append(_check("ip-none", ADDRESS, "fail", f"'{name}' got no address from a radio (169.254.x)",
                              "It joined a network but nothing gave it an address. The radio may still be booting "
                              "(about a minute after power); wired, use the radio's DS port; or the radio isn't "
                              "configured yet (open http://radio.local/)."))
        elif ip.startswith("192.168.69."):
            out.append(_check("ip-setup", ADDRESS, "warn", f"'{name}' is set to {ip}, the address for setting up a radio",
                              ("The radio's setup page answers at http://192.168.69.1/. " if a.get("radio_up") else "")
                              + "Set it back to automatic (DHCP) when the radio is configured, or the Driver Station "
                              "can't reach the robot through it."))
        elif ip.startswith("10.0.1."):
            out.append(_check("ip-factory", ADDRESS, "fail", f"'{name}' is on 10.0.1.x: a radio on its factory setting (team 1)",
                              f"Configure that radio for team {team}: Robot Radio Mode (or Access Point Mode for the "
                              "one at home), team number, suffix and keys, at http://radio.local/."))
        elif ip.startswith(ours + "."):
            host = int(ip.rsplit(".", 1)[1])
            if dhcp:
                out.append(_check("ip-config", ADDRESS, "ok", f"'{name}' gets {ip} from the radio", "Automatic (DHCP): right at home and on the field."))
            elif host == 5 and prefix == 8:
                out.append(_check("ip-config", ADDRESS, "ok", f"'{name}' is set by hand to {ip}, mask 255.0.0.0",
                                  "The field's static Driver Station address."))
            elif host in (1, 2, 3, 4):
                what = {1: "the robot radio", 2: "the robot", 3: "a reserved address", 4: "the access point radio"}[host]
                out.append(_check("ip-config", ADDRESS, "fail", f"'{name}' is set by hand to {ip}, which is {what}'s",
                                  f"Two devices on one address both fail. Set it to automatic (DHCP), or {ours}.5 with "
                                  "mask 255.0.0.0."))
            elif host >= 20:
                out.append(_check("ip-config", ADDRESS, "warn", f"'{name}' is set by hand to {ip}, inside a range radios hand out",
                                  f"The field or the radio can give that address to another device. Use automatic "
                                  f"(DHCP), or {ours}.5 with mask 255.0.0.0."))
            elif prefix == 24 and gw != ours + ".4":
                out.append(_check("ip-config", ADDRESS, "warn", f"'{name}' is set by hand to {ip}, mask 255.255.255.0, no gateway {ours}.4",
                                  "Fine at home, but on the field it can't reach the field's computers. Use mask "
                                  f"255.0.0.0, or keep 255.255.255.0 with gateway {ours}.4."))
            else:
                out.append(_check("ip-config", ADDRESS, "ok", f"'{name}' is set by hand to {ip}",
                                  f"Works. Automatic (DHCP), or {ours}.5 with mask 255.0.0.0, is what the field expects."))
        else:
            other = team_of(ip)
            # A radio's network is a /24 (or a field Driver Station's /8 at .5); a school's 10.x network isn't.
            looks_frc = other and (prefix == 24 or (prefix == 8 and ip.endswith(".5")))
            if looks_frc and other != int(team):
                if dhcp:
                    up = " (its radio answers)" if a.get("radio_up") else ""
                    out.append(_check("ip-other-team", ADDRESS, "fail", f"A radio set for team {other} gave '{name}' {ip}{up}",
                                      f"That radio is configured for team {other}, not {team}: borrowed, set for another "
                                      f"team at an event, or another team's network. Join this robot's, or set the radio to "
                                      f"{team} at http://radio.local/."))
                else:
                    out.append(_check("ip-other-team", ADDRESS, "fail", f"'{name}' is set by hand to team {other}'s network ({ip})",
                                      f"Set it to automatic (DHCP), or {ours}.5 with mask 255.0.0.0 for team {team}."))
        ssid = str(a.get("ssid") or "")
        m = re.fullmatch(r"FRC-(\d+)(?:-.*)?", ssid)
        if m and int(m.group(1)) != int(team):
            out.append(_check("wifi-other-team", ADDRESS, "fail", f"'{name}' joined '{ssid}', team {m.group(1)}'s radio",
                              f"Join team {team}'s network instead."))
        elif a.get("robot") and ssid:
            out.append(_check("wifi", ADDRESS, "info", f"'{name}' is on the Wi-Fi network '{ssid}'", "The robot's network."))
    return out


# ---------------------------------------------------------------------------- the firewall
def _profile(category):
    c = str(category or "")
    return "Domain" if c.startswith("Domain") else c if c in ("Public", "Private") else ""


def firewall(fw, ds_installed):
    fw = fw or {}
    out = []
    others = [o for o in fw.get("others") or [] if o and not re.search(r"(Windows|Microsoft) Defender", o)]
    if others:
        out.append(_check("fw-other", FIREWALL, "warn", "Another firewall is running: " + ", ".join(others),
                          "It can block the Driver Station even when Windows Firewall allows it. Allow the Driver "
                          "Station in it too, or turn it off while on the robot's network."))
    if not ds_installed:
        return out
    profiles = fw.get("profiles") or {}
    robot = _profile(fw.get("robot_profile"))
    which = [robot] if robot else [p for p in ("Public", "Private") if profiles.get(p)]
    if robot and not profiles.get(robot):
        out.append(_check("fw-ds", FIREWALL, "ok", f"Windows Firewall is off for {robot} networks, the robot's", "Nothing there blocks the Driver Station."))
        return out
    if not which:
        out.append(_check("fw-ds", FIREWALL, "ok", "Windows Firewall is off", "Nothing there blocks the Driver Station."))
        return out
    rules = [r for r in fw.get("ds_rules") or [] if r.get("enabled") and str(r.get("direction")) == "Inbound"]

    def covers(r, p):
        prof = str(r.get("profile") or "")
        return prof == "Any" or p in prof

    # One line for the robot's kind of network; off it, one line for every kind still not allowed.
    blocked = {p: [r for r in rules if str(r.get("action")) == "Block" and covers(r, p)] for p in which}
    allowed = {p: any(str(r.get("action")) == "Allow" and covers(r, p) for r in rules) for p in which}
    suffix = ", the robot's" if robot else ""
    bad = [p for p in which if blocked[p]]
    missing = [p for p in which if not blocked[p] and not allowed[p]]
    if bad:
        rule = blocked[bad[0]][0].get("name")
        out.append(_check("fw-ds", FIREWALL, "fail", f"A Windows Firewall rule blocks the Driver Station on {' and '.join(bad)} networks{suffix}",
                          f"Turn off the rule '{rule}' (Windows Defender Firewall, Advanced settings, Inbound Rules). "
                          "The Driver Station then shows communications but no robot code, or nothing."))
    elif missing:
        out.append(_check("fw-ds", FIREWALL, "fail" if robot else "warn",
                          f"Windows Firewall has no rule letting the Driver Station in on {' or '.join(missing)} networks{suffix}",
                          "The robot's replies get blocked: communications but no robot code, or nothing. In Windows "
                          "Security, Firewall, Allow an app through firewall: tick Driver Station for Private and "
                          "Public. (Windows asks the first time it runs: allow both.)"))
    else:
        out.append(_check("fw-ds", FIREWALL, "ok", f"Windows Firewall lets the Driver Station in on {' and '.join(which)} networks{suffix}",
                          "Its rule allows it."))
    return out


# ---------------------------------------------------------------------------- the radio
def firmware(page):
    """The radio's firmware version from its configuration page's text, or None."""
    m = re.search(r"(?i)(?:firmware|version)[^0-9]{0,40}v?(\d+)\.(\d+)\.(\d+)", str(page or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def radio(reach, page, team):
    reach = reach or {}
    out = []
    ours = subnet(team)
    if reach.get("robot_radio") is False and reach.get("ap_radio"):
        out.append(_check("radio-link", RADIO, "fail", "The access point radio answers; the robot radio doesn't",
                          f"The robot radio hasn't linked to the access point. On the robot radio, the SYS light blinking "
                          f"once a second means it can't reach {ours}.4. Most often it still has the last event's "
                          "settings from the kiosk, or a different team number, suffix or key from the access point's. "
                          "Set it again: Ethernet into its DS port, http://radio.local/ (or 192.168.69.1 with this laptop "
                          f"at 192.168.69.2), Robot Radio Mode, team {team}, the same suffix and keys as the access "
                          "point. Or the robot is still booting: give it a minute."))
    elif reach.get("robot_radio"):
        out.append(_check("radio-link", RADIO, "ok", f"The robot radio ({ours}.1) answers", "It is up and linked."))
    if reach.get("robot_radio") and page:
        v = firmware(page)
        if v is None:
            out.append(_check("radio-firmware", RADIO, "warn", "The radio's page shows no firmware version",
                              "That means firmware before 1.2.0. Events have required 1.3.0 or newer since 2025: update "
                              "it from Vivid-Hosting's releases on its page (about 3 minutes; don't cut its power)."))
        elif v < MIN_FIRMWARE:
            out.append(_check("radio-firmware", RADIO, "warn", f"Radio firmware {'.'.join(map(str, v))}",
                              "Events have required 1.3.0 or newer since 2025. Update it from Vivid-Hosting's releases "
                              "on its page (about 3 minutes; don't cut its power)."))
        else:
            out.append(_check("radio-firmware", RADIO, "ok", f"Radio firmware {'.'.join(map(str, v))}", "1.3.0 or newer."))
    return out


# ---------------------------------------------------------------------------- the robot's own software
def accepted_images(project):
    """The roboRIO images the project's GradleRIO accepts at deploy, from its jar in Gradle's cache."""
    import zipfile
    try:
        src = open(os.path.join(project.path, "build.gradle"), encoding="utf-8").read()
    except (OSError, AttributeError):
        return []
    m = re.search(r'id\s+"edu\.wpi\.first\.GradleRIO"\s+version\s+"([^"]+)"', src)
    if not m:
        return []
    jars = glob.glob(os.path.join(os.path.expanduser("~"), ".gradle", "caches", "modules-2", "files-2.1",
                                  "edu.wpi.first", "GradleRIO", m.group(1), "*", f"GradleRIO-{m.group(1)}.jar"))
    for j in jars:
        try:
            with zipfile.ZipFile(j) as z:
                names = [n for n in z.namelist() if n.endswith("WPIExtension.class")]
                found = sorted({x.decode() for n in names for x in re.findall(rb"20\d\d_v\d+(?:\.\d+)?", z.read(n))})
                if found:
                    return found
        except (OSError, zipfile.BadZipFile):
            continue
    return []


def robot_software(image, wpilib, year, accepted=()):
    """The roboRIO's image and the WPILib the running code was built with, from the robot itself."""
    out = []
    m = re.search(r"(20\d\d)_v\d+(?:\.\d+)?", str(image or ""))
    if m:
        img = m.group(0)
        if year and int(m.group(1)) != int(year):
            out.append(_check("robot-image", ROBOT, "fail", f"roboRIO image {img}, but the robot code is {year}",
                              f"Image the roboRIO for {year} with the roboRIO Imaging Tool (FRC Game Tools {year})."))
        elif accepted and not any(img == a or img.startswith(a + ".") or img.startswith(a) for a in accepted):
            out.append(_check("robot-image", ROBOT, "warn", f"roboRIO image {img}: deploy accepts {', '.join(accepted)}",
                              "GradleRIO refuses to deploy to any other image. Image the roboRIO with the newest one."))
        else:
            out.append(_check("robot-image", ROBOT, "ok", f"roboRIO image {img}", "The year the robot code is for."))
    if wpilib:
        out.append(_check("robot-wpilib", ROBOT, "info", f"The robot runs code built with WPILib {wpilib}", "From the code itself."))
    return out


def checks(out, team, year=None, robot=None, accepted=()):
    """Every check for a network-check result: the script's own, then these, each with its group,
    in the page's order. ``robot`` is ``{"image", "wpilib"}`` from the connected robot."""
    facts = out.get("facts") or {}
    mine = []
    if facts:
        ds = facts.get("ds") or {}
        mine += driver_station(ds, team, year)
        mine += addresses(facts.get("adapters"), team, out.get("internet_adapter") or "")
        mine += firewall(facts.get("firewall"), ds.get("installed"))
        mine += radio(facts.get("reach"), facts.get("radio_page"), team)
    if robot:
        mine += robot_software(robot.get("image"), robot.get("wpilib"), year, accepted)
    base = [dict(c, group=SCRIPT_GROUPS.get(c.get("id"), ADDRESS)) for c in out.get("checks") or []
            # The script's one-line firewall hint gives way to the firewall checks above.
            if not (facts and c.get("id") == "firewall")]
    every = base + mine
    return sorted(every, key=lambda c: ORDER.index(c["group"]) if c["group"] in ORDER else len(ORDER))
