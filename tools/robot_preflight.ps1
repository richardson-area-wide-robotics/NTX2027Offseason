<#
.SYNOPSIS
  Checks that robot traffic will actually reach the robot, before you rely on it.

.DESCRIPTION
  Run this FIRST in the shop, once both NICs are up. It exists because of one specific failure
  mode: with a VPN NIC and a robot NIC in the same laptop, robot traffic can silently leave via
  the wrong interface. The Driver Station then shows no robot, or worse, shows an intermittent
  one, and nothing in the routing table looks obviously wrong.

  Windows picks a route by longest prefix match first, then by metric. That usually saves you:
  the robot NIC gets a connected /24 for 10.TE.AM.0, which beats a VPN's 0.0.0.0/0 or even a
  10.0.0.0/8 that a corporate VPN advertises.

  What it does NOT save you from is a VPN client that enforces full tunnelling at the driver
  level — Zscaler, GlobalProtect and some AnyConnect profiles have a kill-switch mode that drops
  non-tunnel traffic regardless of routes. The routing table looks perfect and the packets die
  anyway. That is why this script pings rather than only reading routes: the check has to be
  empirical.

  The same addresses work for SystemCore in 2027: it keeps 10.TE.AM.2, though its hostname is
  always "robot" rather than roborio-TEAM-frc.

.PARAMETER Team
  The team number the robot is set to. Peashooter is 1745; Black team's project says 9990.

.EXAMPLE
  pwsh -File tools/robot_preflight.ps1
  pwsh -File tools/robot_preflight.ps1 -Team 9990
#>
param([int]$Team = 1745)

$TeamNumber = $Team
$Te         = [math]::Floor($Team / 100)
$Am         = $Team % 100
$Subnet     = "10.$Te.$Am"
$RoboRio    = "$Subnet.2"     # 10.TE.AM.2
$Radio      = "$Subnet.1"

function Section($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Good($m)    { Write-Host "  [ok]   $m" -ForegroundColor Green }
function Warn($m)    { Write-Host "  [warn] $m" -ForegroundColor Yellow }
function Bad($m)     { Write-Host "  [FAIL] $m" -ForegroundColor Red }

Write-Host "Robot preflight — team $TeamNumber, roboRIO $RoboRio" -ForegroundColor White

# ---------------------------------------------------------------- interfaces
Section "Connected interfaces, by metric (lower wins ties)"
Get-NetIPInterface -AddressFamily IPv4 |
    Where-Object ConnectionState -eq 'Connected' |
    Sort-Object InterfaceMetric |
    Format-Table ifIndex, InterfaceAlias, InterfaceMetric -AutoSize | Out-String -Width 200 | Write-Host

Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.AddressState -eq 'Preferred' } |
    Format-Table InterfaceAlias, IPAddress, PrefixLength -AutoSize | Out-String -Width 200 | Write-Host

# ---------------------------------------------------------------- which NIC carries robot traffic
Section "Which interface would carry traffic to the roboRIO"
$route = Find-NetRoute -RemoteIPAddress $RoboRio -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $route) {
    Bad "No route to $RoboRio at all. Is the robot NIC up and addressed?"
} else {
    $alias = $route.InterfaceAlias
    Write-Host "  chosen interface : $alias"
    Write-Host "  local source IP  : $($route.IPAddress)"

    # A source address on the robot subnet means the robot NIC won. Anything else means it did not.
    if ($route.IPAddress -like "$Subnet.*") {
        Good "Source address is on the robot subnet — the robot NIC won the route"
    } elseif ($route.IPAddress -like "169.254.*") {
        Warn "Source is link-local ($($route.IPAddress)). The NIC is up but got no DHCP lease from"
        Warn "the radio. Either wait, or set a static $Subnet.5 / 255.255.255.0 on that NIC."
    } else {
        Bad "Robot traffic is leaving via '$alias' with source $($route.IPAddress)."
        Bad "That is NOT the robot NIC. See the fix at the bottom of this output."
    }

    # Flag the usual VPN adapter names.
    if ($alias -match 'VPN|Zscaler|GlobalProtect|AnyConnect|WireGuard|OpenVPN|TAP|Tailscale|WAN Miniport') {
        Bad "The chosen interface looks like a VPN adapter. Robot traffic is going down the tunnel."
    }
}

# ---------------------------------------------------------------- competing routes
Section "Routes that could compete for 10.x traffic"
$competing = Get-NetRoute -AddressFamily IPv4 |
    Where-Object { $_.DestinationPrefix -like '10.*' -or $_.DestinationPrefix -eq '0.0.0.0/0' -or
                   $_.DestinationPrefix -eq '0.0.0.0/1' -or $_.DestinationPrefix -eq '128.0.0.0/1' }

$competing | Sort-Object { [int]($_.DestinationPrefix -split '/')[1] } -Descending |
    Format-Table DestinationPrefix, InterfaceAlias, NextHop, RouteMetric, InterfaceMetric -AutoSize |
    Out-String -Width 200 | Write-Host

if ($competing | Where-Object DestinationPrefix -in '0.0.0.0/1','128.0.0.0/1') {
    Warn "A 0.0.0.0/1 + 128.0.0.0/1 pair is present — that is a full-tunnel VPN beating the default"
    Warn "route without replacing it. Harmless for the robot: a connected /24 is still more specific."
}

# ---------------------------------------------------------------- reachability, the real test
Section "Reachability — this is the check that matters"
foreach ($target in @(@{n="radio";  a=$Radio}, @{n="roboRIO"; a=$RoboRio})) {
    if (Test-Connection -ComputerName $target.a -Count 2 -Quiet -ErrorAction SilentlyContinue) {
        Good "$($target.n) $($target.a) responds to ping"
    } else {
        Bad "$($target.n) $($target.a) does NOT respond"
    }
}

Section "Ports"
# 5810 is NT4. 22 is SSH, for pulling WPILOG files off the roboRIO.
foreach ($p in @(@{n="NT4"; p=5810}, @{n="SSH"; p=22})) {
    $r = Test-NetConnection -ComputerName $RoboRio -Port $p.p -InformationLevel Quiet -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
    if ($r) { Good "$($p.n) port $($p.p) open" }
    else    { Warn "$($p.n) port $($p.p) closed — normal if the robot code is not running yet" }
}

# ---------------------------------------------------------------- mDNS
Section "Name resolution"
Warn "Prefer the literal $RoboRio over roborio-$TeamNumber-frc.local."
Warn "mDNS is unreliable with several NICs up: the query goes out every interface and the first"
Warn "answer wins, which may be the wrong one or none at all."

# ---------------------------------------------------------------- what to do about it
Section "If robot traffic is on the wrong interface"
Write-Host @"
  Two fixes, in order of preference (robot subnet $Subnet.0/24).

  1. Add a specific route for the robot subnet, pinned to the robot NIC. Longest prefix match
     means a /24 beats anything the VPN advertises short of the same /24:

       # find the robot NIC's ifIndex from the table above, then, as Administrator:
       New-NetRoute -DestinationPrefix $Subnet.0/24 -InterfaceIndex <ifIndex> -RouteMetric 1

     Remove it afterwards with Remove-NetRoute -DestinationPrefix $Subnet.0/24.

  2. Lower the robot NIC's interface metric so it wins ties:

       Set-NetIPInterface -InterfaceIndex <ifIndex> -InterfaceMetric 1

  If routes look correct and pings still fail, the VPN client is enforcing full tunnelling
  below the routing layer. No route will fix that — disconnect the VPN while testing. That is
  the case this script cannot work around, only identify.
"@
Write-Host ""
