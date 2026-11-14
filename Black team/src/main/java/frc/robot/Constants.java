package frc.robot;

import edu.wpi.first.math.Matrix;
import edu.wpi.first.math.VecBuilder;
import edu.wpi.first.math.numbers.N1;
import edu.wpi.first.math.numbers.N3;

public class Constants {
    
    public static final class Vision {
        public static final double LAST_VISION_MEASURMENT_TIMER = 0.5;
        public static final boolean VISION_ENABLED = true;

        public static final double STD_TRUSTABLE_DISTANCE = 6;

        public static final Matrix<N3, N1> SINGLE_STD =
            VecBuilder.fill(0.5, 0.5, 999999);

        public static final Matrix<N3, N1> MULTI_STD =
            VecBuilder.fill(0.15, 0.15, 999999);
        public static final double[] TAG_WEIGHTS = {1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1}; // how significantly important each tag is

    }
}