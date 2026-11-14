package frc.robot.Subsystems;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.photonvision.EstimatedRobotPose;
import org.photonvision.PhotonCamera;
import org.photonvision.PhotonPoseEstimator;
import org.photonvision.PhotonPoseEstimator.PoseStrategy;
import org.photonvision.PhotonUtils;
import org.photonvision.targeting.PhotonPipelineResult;
import org.photonvision.targeting.PhotonTrackedTarget;

import edu.wpi.first.apriltag.AprilTagFieldLayout;
import edu.wpi.first.apriltag.AprilTagFields;
import edu.wpi.first.math.Matrix;
import edu.wpi.first.math.geometry.Pose3d;
import edu.wpi.first.math.geometry.Rotation3d;
import edu.wpi.first.math.geometry.Transform3d;
import edu.wpi.first.math.numbers.N1;
import edu.wpi.first.math.numbers.N3;
import edu.wpi.first.wpilibj.Timer;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.robot.Constants;


public class Vision extends SubsystemBase{
    String cameraName = "OV9281";
    PhotonCamera camera;
    AprilTagFieldLayout aprilTagFieldLayout;
    Transform3d cameraPosition = new Transform3d(0,0,0, new Rotation3d()); //the relative coords of the camera to the 3d center of the robot

    PhotonPoseEstimator poseEstimator;
    public List<EstimatedRobotPose> poseEstimations  = new ArrayList<>();
    public List<Double> poseEstimationsTimestamps = new ArrayList<>();
    


    public Vision() {
    camera = new PhotonCamera(cameraName);

    if(!camera.isConnected()) { System.out.println("camera did not connect");}

    aprilTagFieldLayout = AprilTagFieldLayout.loadField(AprilTagFields.k2026RebuiltAndymark);

    poseEstimator = new PhotonPoseEstimator(aprilTagFieldLayout, PoseStrategy.MULTI_TAG_PNP_ON_COPROCESSOR, cameraPosition);
    }



private void updateVisionEstimate(List<PhotonPipelineResult> results){
    for (PhotonPipelineResult result : results){
        Optional<EstimatedRobotPose> estimation = poseEstimator.estimateCoprocMultiTagPose(result);
        if(estimation.isEmpty()) continue;
        poseEstimations.add(estimation.get());
        poseEstimationsTimestamps.add(result.getTimestampSeconds());
    }
}

public void clearResults(){ //called by drive after query
    poseEstimations.clear();
    poseEstimationsTimestamps.clear();
}

public List<Matrix<N3, N1>> calculateStdDeviations(){

    
    List<Matrix<N3, N1>> stdDeviatinMatrices = new ArrayList<>();

    for( EstimatedRobotPose pose : poseEstimations){
        var estStdDevs = Constants.Vision.SINGLE_STD;
        int numTags = 0;
        double averageDistance = 0;
        double averageWeight = 0;
        for (PhotonTrackedTarget target : pose.targetsUsed){
            var tagPose = aprilTagFieldLayout.getTagPose(target.getFiducialId());
            if (tagPose.isEmpty()) continue;
            numTags++;
            averageDistance += target.getBestCameraToTarget().getTranslation().getNorm();
            averageWeight += Constants.Vision.TAG_WEIGHTS[target.getFiducialId() - 1];
        }
        if (numTags == 0) {stdDeviatinMatrices.add(estStdDevs); continue;}; // if there are no tags dont change the std dev. 
        averageDistance /= numTags; // average
        averageWeight /= numTags; // average

        if(numTags > 1) estStdDevs = Constants.Vision.MULTI_STD;
        estStdDevs = estStdDevs.times(1 + (averageDistance * averageDistance / 30)); //sqaure distance divided by constant value

        estStdDevs = estStdDevs.times(averageWeight);

        stdDeviatinMatrices.add(estStdDevs);
    }
    return stdDeviatinMatrices;
}


@Override
public void periodic(){
    List<PhotonPipelineResult> results = camera.getAllUnreadResults();
    updateVisionEstimate(results); 
    if(!camera.isConnected()) camera = new PhotonCamera(cameraName);
}

}