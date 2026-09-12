# Set up YAGSL

Here's what you'll need to do to set up YAGSL in this repo. If you need help, refer to the lesson video, where we did much of this live!

1. Install YAGSL and any other required vendor dependencies. A swerve config with REV motors and a navX is already provided in the deploy folder.
2. Create a Drive subsystem, and create the SwerveDrive object using the config in the deploy folder.
3. Create a drive command that runs as Drive's default command in teleop. This command should let you move forward, backwards, left, right, and spin left and right (you may pick whatever controls you want). You should also be able to click a controller button to toggle between field relative and robot relative mode. 

Make sure all of your controls work in sim!