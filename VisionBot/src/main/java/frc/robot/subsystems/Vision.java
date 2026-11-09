package frc.robot.subsystems;

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

import edu.wpi.first.apriltag.AprilTag;
import edu.wpi.first.apriltag.AprilTagFieldLayout;
import edu.wpi.first.apriltag.AprilTagFields;
import edu.wpi.first.math.Matrix;
import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Pose3d;
import edu.wpi.first.math.geometry.Rotation2d;
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
    List<EstimatedRobotPose> poseEstimations  = new ArrayList<>();


    public Vision() {
    camera = new PhotonCamera(cameraName);

    if(!camera.isConnected()) { throw new RuntimeException("camera not found");}

    aprilTagFieldLayout = AprilTagFieldLayout.loadField(AprilTagFields.k2026RebuiltAndymark);

    poseEstimator = new PhotonPoseEstimator(aprilTagFieldLayout, PoseStrategy.MULTI_TAG_PNP_ON_COPROCESSOR, cameraPosition);
    }



public Optional<Pose3d> getRobotPose(){
    List<Pose3d> possibleRobotPoses = new ArrayList<>();
    List<Double> confidenceScores = new ArrayList<>();

    for( PhotonPipelineResult result : camera.getAllUnreadResults()){ //for every frame that the camera has detected an april tag in:
        double latency = Timer.getFPGATimestamp() - result.getTimestampSeconds(); //calculate how old the frame is
        double maxAcceptableLatency = 0.5;
        double confidence = Math.max(0.0, 1.0 - (latency / maxAcceptableLatency)); //reduce confidence based on how old the frame is
        if(confidence > 0){ //if the frame is more than 0.5 seconds old discard it
            for( PhotonTrackedTarget target : result.getTargets()){ //for every april tag in the frame: 
                if (aprilTagFieldLayout.getTagPose(target.getFiducialId()).isPresent()) { //if the tag is in the layout
                    Double ambiguity = target.getPoseAmbiguity();
                    Double distance = target.getBestCameraToTarget().getTranslation().getNorm();
                    if (ambiguity < 0 || ambiguity > 0.5) { //skip the tag if its ambiguity score is less than 0 (invalid) or greater than 0.5 (risky)
                        continue; 
                    }
                    Double tagConfidence = confidence * (1.0 - ambiguity); //reduce confidence if the target has bad pose ambiguity
                    tagConfidence /= distance;
                    possibleRobotPoses.add(PhotonUtils.estimateFieldToRobotAprilTag(target.getBestCameraToTarget(), aprilTagFieldLayout.getTagPose(target.getFiducialId()).get(), cameraPosition)); 
                    //add the robot position estimate to the list
                    confidenceScores.add(tagConfidence);
                } else {
                    System.out.println("target is not in this field layout!!"); //otherwise we have the wrong layout
                }
            }
        }
    }
    if(possibleRobotPoses.isEmpty()) return Optional.empty(); //if there arnt any targets detected we stop here with an invalid result
    
    double x = 0;
    double y = 0;
    double z = 0;
    double totalWeight = 0;

    for (int i = 0; i < possibleRobotPoses.size(); i++) {
        Pose3d pose = possibleRobotPoses.get(i);
        double weight = confidenceScores.get(i);

        x += pose.getX() * weight;
        y += pose.getY() * weight;
        z += pose.getZ() * weight;

        totalWeight += weight;
    }

    x /= totalWeight;
    y /= totalWeight;
    z /= totalWeight;


    return Optional.of(new Pose3d(x,y,z, new Rotation3d())); //return the average estimate 
}

private void updateVisionEstimate(List<PhotonPipelineResult> results){
    poseEstimations.clear();
    for (PhotonPipelineResult result : results){
        Optional<EstimatedRobotPose> estimation = poseEstimator.estimateCoprocMultiTagPose(result);
        if(estimation.isEmpty()) continue;
        poseEstimations.add(estimation.get());
    }
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
}

}
