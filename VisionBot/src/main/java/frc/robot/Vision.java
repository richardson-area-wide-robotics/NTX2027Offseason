package frc.robot;

import org.photonvision.PhotonCamera;

import edu.wpi.first.wpilibj2.command.SubsystemBase;

public class Vision extends SubsystemBase{
    PhotonCamera camera;
    public Vision() {
    camera = new PhotonCamera("OV9281");

    if(!camera.isConnected()) { throw new RuntimeException("camera not found");}
}




}
