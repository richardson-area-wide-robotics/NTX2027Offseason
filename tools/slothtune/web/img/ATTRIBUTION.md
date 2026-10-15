# Images

## frc-control-system-layout-rev.svg

"FRC Control System - REV" (v3.30 RV), by FRC Team 3161 for the WPILib documentation:
<https://docs.wpilib.org/en/stable/docs/controls-overviews/control-system-hardware.html>, file
<https://docs.wpilib.org/en/stable/_images/frc-control-system-layout-rev.svg> (served 2025-02-10).

Licensed under the Creative Commons Attribution 4.0 International License
(<https://creativecommons.org/licenses/by/4.0/>), as is all of the WPILib documentation
(<https://github.com/wpilibsuite/frc-docs/blob/main/license.txt>).

The file here is the original, unchanged. The tool modifies it as it shows it (`../frcmap.js`): it
crops to one area (the PDH, the CAN bus, the main power, the controllers), dims the parts these
robots don't use (pneumatics, Talon SRX, Koors 40, Krakens, the servo), dims everything but the
part a check is about, draws outlines and labels on top (a PDH port's motor and current, where
to probe the CAN bus), and brightens the CAN wiring. Every view says so under it, with the
credit and the license.

## parts/: one part each

From "FRC Control System Diagrams" by FRC Team 3161 (stefacep),
<https://github.com/stefacep/FRC-Control-System-Diagrams>, folder `Individual Components/SVG`
(fetched 2026-10-14, repository updated 2026-10-04). Licensed under the Creative Commons
Attribution 4.0 International License (<https://creativecommons.org/licenses/by/4.0/>). Logos on
some of the drawings belong to their respective owners.

The files are unchanged; only their names are:

| Here | Original |
|---|---|
| `spark-max.svg` | `REV Spark MAX.svg` |
| `spark-flex-on-neo-vortex.svg` | `NEO Vortex.svg` (a SPARK Flex docked on a NEO Vortex) |
| `neo-1.1.svg` | `Neo 1.1.svg` |
| `neo-2.0.svg` | `Neo 2.svg` |
| `neo-550.svg` | `Neo 550.svg` |
| `roborio-2.svg` | `RoboRIO 2.0.svg` |
| `systemcore.svg` | `Systemcore.svg` |
| `pdh.svg` | `PDH (No Fuses).svg` |

The Wiring tab's device cards and the Motors tab show them, credited under each.

`luma-p1.svg` is ours, drawn for this tool in the same style: the Luma P1's lens side, every size
taken from Luma's public drawing ("P1 Assembly Public Drawing", <https://docs.luma.vision/p1/files/P1%20Assembly%20Public%20Drawing.pdf>). The name on it is
the camera's own engraving, as Luma draws it.

## fields/: the field from above

`fields/field26.png` is PathPlanner's 2026 REBUILT field picture, `images/field26.png` from
<https://github.com/mjansen4857/pathplanner> (fetched 2026-10-14), by Michael Jansen and the
PathPlanner contributors, under the MIT License (`fields/LICENSE-PathPlanner.txt`). Here it is at
half its size (1754 x 907 px, so 100 px a meter with PathPlanner's 0.5 m margin) and reduced to
256 colors. The Live tab places the robot on it the way PathPlanner's `field_image.dart` and
`path_painter_util.dart` do. A new season's field: add PathPlanner's new picture the same way and
a line for it in `FIELD_PICS` (`../live.js`); until then the Live tab draws the field plain.

## crimp/ and wire/: drawn for this tool

The crimp drawings (Molex SL, Anderson Powerpole, Anderson SB50: good and bad crimps, orientation
and polarity) and the wire-gauge drawing are original schematics made for Sloth Tune, not copies of
anyone's photos or drawings. Their facts come from, and the lessons link: Molex's SL hand-tool
specification and Quality Crimp Handbook; Anderson Power Products' Powerpole and SB50 data and
assembly sheets; West Mountain Radio's Powerpole crimping manual; frcelectrical.org (Making
Connections, Battery); CTRE's CAN troubleshooting; WPILib's battery and wiring pages; and the 2026
FRC game manual (R609, R622, R624). Copper resistance and diameters: the standard AWG table.
