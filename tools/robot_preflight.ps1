<#
.SYNOPSIS
  Checks this laptop can reach the robot and the internet (Claude, over a VPN) at the same time.

.DESCRIPTION
  The shop setup it is for: the laptop's own Wi-Fi on the school network, with the VPN on it for
  Claude, and a second (USB) Wi-Fi adapter on the robot's radio. Both work at once only if:

   1. Robot traffic (10.TE.AM.x) leaves by the robot adapter. Windows picks the longest matching
      route first, so the robot adapter's own 10.TE.AM.0/24 beats a VPN's 0.0.0.0/0 or 0.0.0.0/1,
      unless the VPN or the school network claims that same subnet.
   2. Everything else leaves by the school Wi-Fi. The robot radio hands out a default gateway like
      any router. If the robot adapter's metric is the lower one, Windows sends the internet there,
      including the VPN's own connection, to a radio with no internet: the VPN drops and Claude
      with it. The robot adapter needs the HIGHER metric (-Fix sets it to 500).
   3. The VPN lets traffic outside the tunnel through. A full-tunnel VPN with a kill switch
      (WireGuard's "Block untunneled traffic", "block local network" in others) drops robot packets
      whatever the routes say. Checked by reaching the school Wi-Fi's own router outside the tunnel.

  At events the robot radio joins the field, so in the pit use an Ethernet cable on a USB Ethernet
  adapter instead of the USB Wi-Fi; everything here applies to it the same way.

  SystemCore (2027) keeps 10.TE.AM.2, so nothing here changes then.

.PARAMETER Team
  The robot's team number: Peashooter 1745, Black team 9990.

.PARAMETER RobotAdapter
  The adapter on the robot's network (its name in Get-NetAdapter, e.g. "Wi-Fi 2"), when it can't be
  found by its address.

.PARAMETER Fix
  Run as Administrator. Sets the robot adapter's metric to 500, so it carries only robot traffic and
  never the internet. Changes nothing else. It stays set for that adapter; undo with
  Set-NetIPInterface -InterfaceAlias "<name>" -AutomaticMetric Enabled

.PARAMETER Json
  Prints one JSON object instead of the report (the swerve tools' "Check the networks" uses it),
  with the facts the swerve tools judge: the Driver Station, each adapter's address, the firewall and
  which radios answer.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\robot_preflight.ps1 -Team 1745
  powershell -ExecutionPolicy Bypass -File tools\robot_preflight.ps1 -Team 1745 -Fix   (as Administrator)
#>
param([int]$Team = 1745, [string]$RobotAdapter = "", [switch]$Fix, [switch]$Json)

$ErrorActionPreference = 'SilentlyContinue'
$Te = [math]::Floor($Team / 100); $Am = $Team % 100
$Subnet = "10.$Te.$Am"; $RoboRio = "$Subnet.2"; $Radio = "$Subnet.1"
$TunnelPattern = 'WireGuard|Wintun|TAP-Windows|VPN|Zscaler|GlobalProtect|PANGP|AnyConnect|Cisco|Tailscale|OpenVPN|Fortinet|WAN Miniport|ZeroTier'
$Checks = New-Object System.Collections.ArrayList

function Add-Check($id, $level, $title, $why) {
    [void]$Checks.Add([ordered]@{ id = $id; level = $level; title = $title; why = $why })
}

function IpNum([string]$ip) {
    $b = ([System.Net.IPAddress]::Parse($ip)).GetAddressBytes()
    return [int64]$b[0] * 16777216 + [int64]$b[1] * 65536 + [int64]$b[2] * 256 + [int64]$b[3]
}

# Whether two prefixes overlap: the shorter one contains the other's network address.
function Overlaps([string]$a, [int]$alen, [string]$b, [int]$blen) {
    $len = [math]::Min($alen, $blen)
    $size = [math]::Pow(2, 32 - $len)
    return [math]::Floor((IpNum $a) / $size) -eq [math]::Floor((IpNum $b) / $size)
}

function Ping-Quiet([string]$addr) {
    try {
        $p = New-Object System.Net.NetworkInformation.Ping
        for ($i = 0; $i -lt 2; $i++) { if ($p.Send($addr, 800).Status -eq 'Success') { return $true } }
    } catch { }
    return $false
}

function Test-Tcp([string]$addr, [int]$port, [int]$ms = 1500) {
    $c = New-Object System.Net.Sockets.TcpClient
    try { $t = $c.ConnectAsync($addr, $port); return ($t.Wait($ms) -and $c.Connected) }
    catch { return $false } finally { $c.Dispose() }
}

function Resolve-V4([string]$name) {
    try { return ([System.Net.Dns]::GetHostAddresses($name) | Where-Object AddressFamily -eq 'InterNetwork' |
                  Select-Object -First 1).IPAddressToString } catch { return $null }
}

function Get-State {
    $adapters = @{}
    Get-NetAdapter | ForEach-Object { $adapters[[int]$_.ifIndex] = $_ }
    $ifs = @{}
    Get-NetIPInterface -AddressFamily IPv4 | ForEach-Object { $ifs[[int]$_.ifIndex] = $_ }
    $addrs = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.AddressState -eq 'Preferred' })
    $routes = @(Get-NetRoute -AddressFamily IPv4)
    return @{ adapters = $adapters; ifs = $ifs; addrs = $addrs; routes = $routes }
}

function Is-Tunnel($st, [int]$idx) {
    $a = $st.adapters[$idx]
    return $a -and (($a.InterfaceDescription + ' ' + $a.Name) -match $TunnelPattern)
}

function Effective($st, $route) {
    $i = $st.ifs[[int]$route.ifIndex]
    return [int]$route.RouteMetric + $(if ($i) { [int]$i.InterfaceMetric } else { 0 })
}

function Find-RobotAdapter($st) {
    if ($RobotAdapter) {
        $a = Get-NetAdapter -Name $RobotAdapter
        if ($a) { return [int]$a.ifIndex }
    }
    $hit = $st.addrs | Where-Object { $_.IPAddress -like "$Subnet.*" } | Select-Object -First 1
    if ($hit) { return [int]$hit.InterfaceIndex }
    return $null
}

# ---------------------------------------------------------------- -Fix
$st = Get-State
$robotIdx = Find-RobotAdapter $st
$fixed = $null
if ($Fix) {
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) {
        $fixed = "Not changed: -Fix needs PowerShell run as Administrator."
    } elseif ($null -eq $robotIdx) {
        $fixed = "Not changed: no adapter on the robot's network ($Subnet.x) yet. Join the robot's Wi-Fi with the USB adapter first, or name it with -RobotAdapter."
    } else {
        Set-NetIPInterface -InterfaceIndex $robotIdx -AddressFamily IPv4 -InterfaceMetric 500 -ErrorAction Stop
        $fixed = "Set '$($st.adapters[$robotIdx].Name)' to metric 500: it now carries only robot traffic. Undo: Set-NetIPInterface -InterfaceAlias '$($st.adapters[$robotIdx].Name)' -AutomaticMetric Enabled"
        Start-Sleep -Seconds 2
        $st = Get-State
        $robotIdx = Find-RobotAdapter $st
    }
}

# ---------------------------------------------------------------- the internet side
$defaults = @($st.routes | Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' })
$school = $defaults | Where-Object { $_.ifIndex -ne $robotIdx -and -not (Is-Tunnel $st $_.ifIndex) } |
    Sort-Object { Effective $st $_ } | Select-Object -First 1
$schoolIdx = if ($school) { [int]$school.ifIndex } else { $null }
$schoolName = if ($school) { $st.adapters[$schoolIdx].Name } else { "" }
$tunnels = @($st.addrs | ForEach-Object { [int]$_.InterfaceIndex } | Sort-Object -Unique | Where-Object { Is-Tunnel $st $_ })
$fullTunnel = @($tunnels | Where-Object {
    $t = $_
    @($st.routes | Where-Object { $_.ifIndex -eq $t -and $_.DestinationPrefix -in '0.0.0.0/0', '0.0.0.0/1', '128.0.0.0/1' }).Count -gt 0 })
$vpnName = if ($tunnels.Count) { $st.adapters[[int]$tunnels[0]].Name } else { "" }

if (-not $school) {
    Add-Check "internet" "fail" "No internet connection besides the robot's" "Connect the laptop's own Wi-Fi to the school network first; the robot's radio has no internet."
} else {
    Add-Check "internet" "ok" "Internet: '$schoolName' (router $($school.NextHop))" "The school Wi-Fi carries everything that isn't for the robot."
}

if ($tunnels.Count) {
    $how = if ($fullTunnel.Count) { "a full tunnel: everything but the robot goes through it" } else { "a split tunnel" }
    Add-Check "vpn" "info" "VPN: '$vpnName', $how" "Claude is reached through it; the robot never is."
}

$claudeIp = Resolve-V4 "api.anthropic.com"
if (-not $claudeIp) {
    Add-Check "claude" "fail" "Can't look up api.anthropic.com" "No working DNS for the internet. Check the school Wi-Fi and the VPN are connected."
} else {
    $cr = Find-NetRoute -RemoteIPAddress $claudeIp | Select-Object -First 1
    $via = if ($cr) { $st.adapters[[int]$cr.InterfaceIndex].Name } else { "?" }
    if ($cr -and [int]$cr.InterfaceIndex -eq $robotIdx) {
        Add-Check "claude-route" "fail" "Claude's traffic is going to the robot's radio" "The robot adapter has the lower metric, so the internet goes there and nowhere. Run this script with -Fix as Administrator."
    } elseif (Test-Tcp $claudeIp 443 3000) {
        Add-Check "claude" "ok" "Claude reachable through '$via'" "api.anthropic.com answers on port 443."
    } else {
        Add-Check "claude" "fail" "Claude not reachable (through '$via')" "api.anthropic.com doesn't answer on port 443. Is the VPN connected? The school network blocks it without the VPN."
    }
}

# A kill switch drops traffic outside the tunnel, the robot's included: reach the school router outside it.
if ($fullTunnel.Count -and $school) {
    $lanVia = (Find-NetRoute -RemoteIPAddress $school.NextHop | Select-Object -First 1).InterfaceIndex
    if ([int]$lanVia -eq $schoolIdx) {
        if (Ping-Quiet $school.NextHop) {
            Add-Check "killswitch" "ok" "The VPN lets traffic outside the tunnel through" "The school Wi-Fi's own router answers outside the VPN, so robot traffic will get through too."
        } else {
            Add-Check "killswitch" "warn" "The VPN may block traffic outside the tunnel" "The school Wi-Fi's router ($($school.NextHop)) didn't answer outside the VPN. Some routers ignore pings; if the robot doesn't answer below either, turn off the VPN's kill switch (WireGuard: Edit the tunnel, untick 'Block untunneled traffic (kill-switch)'; other VPNs: allow local network access, or split tunneling)."
        }
    }
}

# ---------------------------------------------------------------- the robot side
if ($null -eq $robotIdx) {
    $spare = @(Get-NetAdapter | Where-Object { $_.MediaType -eq 'Native 802.11' -and $_.ifIndex -ne $schoolIdx })
    $hint = if ($spare.Count) { "Join the robot's Wi-Fi with '$($spare[0].Name)' (in the Wi-Fi menu, pick that adapter from the list at the top)." } else { "Plug in the USB Wi-Fi adapter and join the robot's Wi-Fi with it." }
    $link = $st.addrs | Where-Object { $_.IPAddress -like '169.254.*' -and -not (Is-Tunnel $st $_.InterfaceIndex) } | Select-Object -First 1
    if ($link) { $hint += " '$($st.adapters[[int]$link.InterfaceIndex].Name)' has no address from a radio yet (169.254.x): wait a few seconds, or check it joined the right network." }
    Add-Check "robot-adapter" "warn" "No adapter on the robot's network ($Subnet.x) yet" $hint
} else {
    $rname = $st.adapters[$robotIdx].Name
    $rip = ($st.addrs | Where-Object { [int]$_.InterfaceIndex -eq $robotIdx } | Select-Object -First 1).IPAddress
    if ($rip -like "$Subnet.*") {
        Add-Check "robot-adapter" "ok" "Robot network: '$rname' ($rip)" "Robot traffic for $Subnet.x uses this adapter."
    } else {
        $has = if ($rip) { "has $rip" } else { "has no address" }
        Add-Check "robot-adapter" "fail" "'$rname' isn't on the robot's network" "It $has, not $Subnet.x: it hasn't joined the robot's radio, or the radio gave it no address yet. Check the team number too (Peashooter 1745, Black team 9990)."
    }

    $rr = Find-NetRoute -RemoteIPAddress $RoboRio | Select-Object -First 1
    if ($rr -and [int]$rr.InterfaceIndex -eq $robotIdx) {
        Add-Check "robot-route" "ok" "Robot traffic goes out '$rname'" "The robot's own $Subnet.0/24 route wins over the VPN's."
    } else {
        $other = if ($rr) { $st.adapters[[int]$rr.InterfaceIndex].Name } else { "nowhere" }
        $why = if ($rip -like "$Subnet.*") { "Something claims the robot's subnet ahead of the robot adapter: see the overlap check." }
               else { "'$rname' has no route to $Subnet.x until it is on the robot's network." }
        Add-Check "robot-route" "fail" "Robot traffic goes out '$other', not '$rname'" $why
    }

    # The robot radio's default gateway must never win: the VPN's connection would follow it.
    $rdef = $defaults | Where-Object { [int]$_.ifIndex -eq $robotIdx } | Select-Object -First 1
    $rmetric = [int]$st.ifs[$robotIdx].InterfaceMetric
    if (-not $rdef) {
        Add-Check "robot-metric" "ok" "The robot's radio gave no internet gateway" "Nothing but robot traffic can go to it."
    } elseif ($school -and (Effective $st $rdef) -le (Effective $st $school)) {
        Add-Check "robot-metric" "fail" "The internet can go to the robot's radio" "'$rname' (metric $rmetric) wins over '$schoolName' (metric $([int]$st.ifs[$schoolIdx].InterfaceMetric)) for the internet, and the VPN's own connection would follow it to a radio with no internet. Run this script with -Fix as Administrator (sets '$rname' to metric 500)."
    } elseif ($rmetric -lt 100) {
        Add-Check "robot-metric" "warn" "The robot adapter's metric isn't pinned high" "'$rname' (metric $rmetric) loses to '$schoolName' today, but Windows sets metrics from link speed and a faster robot link could flip it, taking the VPN with it. Run this script once with -Fix as Administrator."
    } else {
        Add-Check "robot-metric" "ok" "The robot adapter never carries the internet" "'$rname' has metric $rmetric, well above '$schoolName'."
    }

    # Something else claiming the robot's subnet: the school network, or a VPN route.
    $clash = @()
    foreach ($a in $st.addrs) {
        if ([int]$a.InterfaceIndex -ne $robotIdx -and (Overlaps $a.IPAddress $a.PrefixLength "$Subnet.0" 24) -and $a.PrefixLength -ge 24) {
            $clash += "'$($st.adapters[[int]$a.InterfaceIndex].Name)' has the address $($a.IPAddress)/$($a.PrefixLength)"
        }
    }
    foreach ($r in $st.routes) {
        $p = $r.DestinationPrefix -split '/'
        if ([int]$r.ifIndex -ne $robotIdx -and [int]$p[1] -ge 24 -and [int]$p[1] -lt 32 -and (Overlaps $p[0] ([int]$p[1]) "$Subnet.0" 24)) {
            $clash += "'$($st.adapters[[int]$r.ifIndex].Name)' routes $($r.DestinationPrefix)"
        }
    }
    if ($clash.Count) {
        Add-Check "overlap" "fail" "Another network uses the robot's addresses" (($clash -join "; ") + ". Routes can't sort that out: use another network for the internet, or ask for the VPN to leave $Subnet.0/24 alone.")
    }

    $radioUp = Ping-Quiet $Radio
    $rioUp = Ping-Quiet $RoboRio
    if ($rioUp) {
        Add-Check "robot-ping" "ok" "The robot ($RoboRio) answers" "The robot and the internet both work from this laptop."
    } elseif ($radioUp) {
        Add-Check "robot-ping" "warn" "The radio answers but the robot ($RoboRio) doesn't" "The robot may still be booting (about 30 s), or the radio-to-robot Ethernet cable is loose."
    } else {
        Add-Check "robot-ping" "fail" "Neither the radio nor the robot answers" "Check the robot is on and '$rname' joined its network. If the routes above are right and it still fails, a VPN kill switch is dropping the packets: turn it off (see the VPN check)."
    }
    if ($rioUp) {
        if (Test-Tcp $RoboRio 5810) { Add-Check "nt4" "ok" "Robot code is running (NetworkTables port 5810 open)" "The swerve tools can connect." }
        else { Add-Check "nt4" "warn" "NetworkTables port 5810 is closed" "Normal while the robot code is starting or not deployed." }
    }
    $prof = Get-NetConnectionProfile -InterfaceIndex $robotIdx
    if ($prof -and $prof.NetworkCategory -eq 'Public') {
        Add-Check "firewall" "info" "Windows calls the robot's network Public" "If the Driver Station shows communications but no robot code while the swerve tools connect fine, Windows Firewall is blocking the Driver Station on Public networks: allow it there (FRC's own troubleshooting does the same)."
    }
}

# ---------------------------------------------------------------- facts for the swerve tools to judge
# The Driver Station, each adapter's addressing, the firewall and the radios, read and never changed.
# The swerve tools (swervetune/station.py) turn these into checks; -Json carries them as "facts".
$facts = [ordered]@{}
if ($Json) {
    $dsExe = Join-Path ${env:ProgramFiles(x86)} 'FRC Driver Station\DriverStation.exe'
    $ds = [ordered]@{ installed = [bool](Test-Path $dsExe); version = ""; running = $false; ini = $false; team = $null; ini_keys = @() }
    if ($ds.installed) { $ds.version = "$((Get-Item $dsExe).VersionInfo.FileVersion)" }
    $ds.running = [bool](Get-Process -Name DriverStation -ErrorAction SilentlyContinue)
    $ini = Join-Path $env:PUBLIC 'Documents\FRC\FRC DS Data Storage.ini'
    if (Test-Path $ini) {
        $ds.ini = $true
        $m = Select-String -Path $ini -Pattern '^\s*team\s*_?number\s*=\s*"?(\d+)' | Select-Object -First 1
        if ($m) { $ds.team = [int]$m.Matches[0].Groups[1].Value }
        # The settings' names only, never their values: which one holds the team number.
        $ds.ini_keys = @(Get-Content $ini | ForEach-Object { if ($_ -match '^\s*([^=\[;#]+?)\s*=') { $Matches[1] } })
    }
    $facts.ds = $ds

    # Each Wi-Fi adapter's network name, from netsh (Name, then its SSID; BSSID lines don't match).
    $ssids = @{}; $cur = $null
    foreach ($line in @(netsh wlan show interfaces 2>$null)) {
        if ($line -match '^\s*Name\s*:\s*(.+?)\s*$') { $cur = $Matches[1] }
        elseif ($cur -and $line -match '^\s*SSID\s*:\s*(.+?)\s*$') { $ssids[$cur] = $Matches[1] }
    }
    $adapters = @()
    foreach ($a in @(Get-NetAdapter | Where-Object Status -eq 'Up')) {
        $i = [int]$a.ifIndex
        if (Is-Tunnel $st $i) { continue }
        $ip = Get-NetIPAddress -InterfaceIndex $i -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' } | Select-Object -First 1
        $gw = (Get-NetRoute -InterfaceIndex $i -DestinationPrefix '0.0.0.0/0' | Select-Object -First 1).NextHop
        $rec = [ordered]@{ name = $a.Name; wifi = [bool]($a.MediaType -eq 'Native 802.11'); ip = ""; prefix = 0
                           dhcp = $false; gateway = "$gw"; ssid = "$($ssids[$a.Name])"; robot = [bool]($i -eq $robotIdx); radio_up = $null }
        if ($ip) {
            $rec.ip = $ip.IPAddress; $rec.prefix = [int]$ip.PrefixLength
            $rec.dhcp = [bool]("$($st.ifs[$i].Dhcp)" -eq 'Enabled')
            # Another team's subnet, the radio's factory one (team 1) or its setup address: is a radio there?
            $o = $ip.IPAddress -split '\.'
            if ($ip.IPAddress -like '10.*' -and $ip.IPAddress -notlike "$Subnet.*") { $rec.radio_up = Ping-Quiet "10.$($o[1]).$($o[2]).1" }
            elseif ($ip.IPAddress -like '192.168.69.*') { $rec.radio_up = Ping-Quiet '192.168.69.1' }
        }
        $adapters += $rec
    }
    $facts.adapters = $adapters

    $fw = [ordered]@{ profiles = [ordered]@{}; robot_profile = ""; ds_rules = @(); others = @() }
    foreach ($p in @(Get-NetFirewallProfile)) { $fw.profiles["$($p.Name)"] = [bool]("$($p.Enabled)" -eq 'True') }
    if ($null -ne $robotIdx) { $fw.robot_profile = "$((Get-NetConnectionProfile -InterfaceIndex $robotIdx).NetworkCategory)" }
    foreach ($f in @(Get-NetFirewallApplicationFilter | Where-Object { $_.Program -like '*DriverStation.exe' })) {
        $r = $f | Get-NetFirewallRule
        if ($r) { $fw.ds_rules += [ordered]@{ name = "$($r.DisplayName)"; enabled = [bool]("$($r.Enabled)" -eq 'True')
                                             direction = "$($r.Direction)"; action = "$($r.Action)"; profile = "$($r.Profile)" } }
    }
    # Other firewalls (antivirus suites) register here; Windows' own doesn't.
    $fw.others = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName FirewallProduct | ForEach-Object { "$($_.displayName)" })
    $facts.firewall = $fw

    # The radios, from the robot's network: the robot radio (.1), the access point radio at home (.4).
    $reach = [ordered]@{ robot_radio = $null; ap_radio = $null; roborio = $null }
    $page = ""
    if ($null -ne $robotIdx -and $rip -like "$Subnet.*") {
        $reach.robot_radio = [bool]$radioUp; $reach.roborio = [bool]$rioUp
        $reach.ap_radio = Ping-Quiet "$Subnet.4"
        if ($radioUp) {
            try {
                $w = Invoke-WebRequest -Uri "http://$Radio/" -UseBasicParsing -TimeoutSec 4
                $text = (($w.Content -replace '<[^>]+>', ' ') -replace '\s+', ' ').Trim()
                # Only the words around its firmware version: the rest of the page can show its keys.
                $v = [regex]::Match($text, '(?i).{0,40}(firmware|version).{0,60}')
                $page = if ($v.Success) { $v.Value -replace '(?i)(key|pass\w*|psk|sae)\s*[:=]?\s*\S+', '$1 [hidden]' } else { '(page read; no version on it)' }
            } catch { }
        }
    }
    $facts.reach = $reach
    $facts.radio_page = $page
}

$ok = -not ($Checks | Where-Object { $_.level -eq 'fail' })
if ($Json) {
    [ordered]@{ ok = [bool]$ok; team = $Team; subnet = "$Subnet.0/24"; robot_adapter = $(if ($null -ne $robotIdx) { $st.adapters[$robotIdx].Name } else { "" })
                internet_adapter = $schoolName; vpn = $vpnName; fixed = $fixed; checks = @($Checks); facts = $facts } | ConvertTo-Json -Depth 6
    exit 0
}

Write-Host "Network check: team $Team, robot $RoboRio, and the internet (Claude) at the same time" -ForegroundColor White
if ($fixed) { Write-Host ""; Write-Host "  $fixed" -ForegroundColor Cyan }
Write-Host ""
foreach ($c in $Checks) {
    $color = switch ($c.level) { 'ok' { 'Green' } 'warn' { 'Yellow' } 'fail' { 'Red' } default { 'Gray' } }
    Write-Host ("  [{0,-4}] {1}" -f $c.level.ToUpper(), $c.title) -ForegroundColor $color
    Write-Host "         $($c.why)"
}
Write-Host ""
if ($ok) { Write-Host "Nothing blocking. (Prefer $RoboRio over roborio-$Team-frc.local: with two networks up, mDNS can answer from the wrong one.)" -ForegroundColor Green }
else { Write-Host "Fix the FAIL lines above, then run this again." -ForegroundColor Red }
