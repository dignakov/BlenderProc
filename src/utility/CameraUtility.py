import bpy
import numpy as np
from mathutils import Matrix, Vector, Euler
from typing import Union, Tuple

from src.main.GlobalStorage import GlobalStorage

class CameraUtility:

    @staticmethod
    def add_camera_pose(cam2world_matrix: Union[np.ndarray, Matrix], frame: Union[int, None] = None):
        """ Sets a new camera pose to a new or existing frame

        :param cam2world_matrix: The transformation matrix from camera to world coordinate system
        :param frame: Optional, the frame to set the camera pose to.
        :return: The frame to which the pose has been set.
        """
        if not isinstance(cam2world_matrix, Matrix):
            cam2world_matrix = Matrix(cam2world_matrix)

        # Set cam2world_matrix
        cam_ob = bpy.context.scene.camera
        cam_ob.matrix_world = cam2world_matrix

        # Add new frame if no frame is given
        if frame is None:
            frame = bpy.context.scene.frame_end
        if bpy.context.scene.frame_end < frame + 1:
            bpy.context.scene.frame_end = frame + 1

        # Persist camera pose
        cam_ob.keyframe_insert(data_path='location', frame=frame)
        cam_ob.keyframe_insert(data_path='rotation_euler', frame=frame)

        return frame

    @staticmethod
    def rotation_from_forward_vec(forward_vec: Union[np.ndarray, Vector], up_axis: str = 'Y', inplane_rot: float = None) -> np.ndarray:
        """ Returns a camera rotation matrix for the given forward vector and up axis

        :param forward_vec: The forward vector which specifies the direction the camera should look.
        :param up_axis: The up axis, usually Y.
        :param inplane_rot: The inplane rotation in radians. If None is given, the inplane rotation is determined only based on the up vector.
        :return: The corresponding rotation matrix.
        """
        rotation_matrix = Vector(forward_vec).to_track_quat('-Z', up_axis).to_matrix()
        if inplane_rot is not None:
            rotation_matrix = rotation_matrix @ Euler((0.0, 0.0, inplane_rot)).to_matrix()
        return np.array(rotation_matrix)

    @staticmethod
    def set_intrinsics_from_blender_params(lens, image_width, image_height, clip_start=0.1, clip_end=1000, pixel_aspect_x=1, pixel_aspect_y=1, shift_x=0, shift_y=0, lens_unit="MILLIMETERS"):
        """ Sets the camera intrinsics using blenders represenation.

        :param lens: Either the focal length in millimeters or the FOV in radians, depending on the given lens_unit.
        :param image_width: The image width in pixels.
        :param image_height: The image height in pixels.
        :param clip_start: Clipping start.
        :param clip_end: Clipping end.
        :param pixel_aspect_x: The pixel aspect ratio along x.
        :param pixel_aspect_y: The pixel aspect ratio along y.
        :param shift_x: The shift in x direction.
        :param shift_y: The shift in y direction.
        :param lens_unit: Either FOV or MILLIMETERS depending on whether the lens is defined as focal length in millimeters or as FOV in radians.
        """
        cam_ob = bpy.context.scene.camera
        cam = cam_ob.data

        # Set focal length
        if lens_unit == 'MILLIMETERS':
            cam.lens_unit = lens_unit
            if lens < 1:
                raise Exception("The focal length is smaller than 1mm which is not allowed in blender: " + str(lens))
            cam.lens = lens
        elif lens_unit == "FOV":
            cam.lens_unit = lens_unit
            cam.angle = lens
        else:
            raise Exception("No such lens unit: " + lens_unit)

        # Set resolution
        bpy.context.scene.render.resolution_x = image_width
        bpy.context.scene.render.resolution_y = image_height

        # Set clipping
        cam.clip_start = clip_start
        cam.clip_end = clip_end

        # Set aspect ratio
        bpy.context.scene.render.pixel_aspect_x = pixel_aspect_x
        bpy.context.scene.render.pixel_aspect_y = pixel_aspect_y

        # Set shift
        cam.shift_x = shift_x
        cam.shift_y = shift_y


    @staticmethod
    def set_stereo_parameters(convergence_mode, convergence_distance, interocular_distance):
        """ Sets the stereo parameters of the camera.

        :param convergence_mode: How the two cameras converge (e.g. Off-Axis where both cameras are shifted inwards to converge in the convergence plane, or parallel where they do not converge and are parallel)
        :param convergence_distance: The convergence point for the stereo cameras (i.e. distance from the projector to the projection screen)
        :param interocular_distance: Distance between the camera pair
        """
        cam_ob = bpy.context.scene.camera
        cam = cam_ob.data

        cam.stereo.convergence_mode = convergence_mode
        cam.stereo.convergence_distance = convergence_distance
        cam.stereo.interocular_distance = interocular_distance

    @staticmethod
    def set_intrinsics_from_K_matrix(K: Union[np.ndarray, Matrix], image_width: int, image_height: int, clip_start: float = 0.1, clip_end: int = 1000):
        """ Set the camera intrinsics via a K matrix.

        The K matrix should have the format:
            [[fx, 0, cx],
             [0, fy, cy],
             [0, 0,  1]]

        This method is based on https://blender.stackexchange.com/a/120063.

        :param K: The 3x3 K matrix.
        :param image_width: The image width in pixels.
        :param image_height: The image height in pixels.
        :param clip_start: Clipping start.
        :param clip_end: Clipping end.
        """

        K = Matrix(K)

        cam_ob = bpy.context.scene.camera
        cam = cam_ob.data

        fx, fy = K[0][0], K[1][1]
        cx, cy = K[0][2], K[1][2]

        # If fx!=fy change pixel aspect ratio
        pixel_aspect_x = pixel_aspect_y = 1
        if fx > fy:
            pixel_aspect_y = fx / fy
        elif fx < fy:
            pixel_aspect_x = fy / fx

        # Compute sensor size in mm and view in px
        pixel_aspect_ratio = pixel_aspect_y / pixel_aspect_x
        view_fac_in_px = CameraUtility.get_view_fac_in_px(cam, pixel_aspect_x, pixel_aspect_y, image_width, image_height)
        sensor_size_in_mm = CameraUtility.get_sensor_size(cam)

        # Convert focal length in px to focal length in mm
        f_in_mm = fx * sensor_size_in_mm / view_fac_in_px

        # Convert principal point in px to blenders internal format
        shift_x = (cx - (image_width - 1) / 2) / -view_fac_in_px
        shift_y = (cy - (image_height - 1) / 2) / view_fac_in_px * pixel_aspect_ratio

        # Finally set all intrinsics
        CameraUtility.set_intrinsics_from_blender_params(f_in_mm, image_width, image_height, clip_start, clip_end, pixel_aspect_x, pixel_aspect_y, shift_x, shift_y)

    @staticmethod
    def get_sensor_size(cam):
        """ Returns the sensor size in millimeters based on the configured sensor_fit.

        :param cam: The camera object.
        :return: The sensor size in millimeters.
        """
        if cam.sensor_fit == 'VERTICAL':
            sensor_size_in_mm = cam.sensor_height
        else:
            sensor_size_in_mm = cam.sensor_width
        return sensor_size_in_mm

    @staticmethod
    def get_view_fac_in_px(cam, pixel_aspect_x, pixel_aspect_y, resolution_x_in_px, resolution_y_in_px):
        """ Returns the camera view in pixels.

        :param cam: The camera object.
        :param pixel_aspect_x: The pixel aspect ratio along x.
        :param pixel_aspect_y: The pixel aspect ratio along y.
        :param resolution_x_in_px: The image width in pixels.
        :param resolution_y_in_px: The image height in pixels.
        :return: The camera view in pixels.
        """
        # Determine the sensor fit mode to use
        if cam.sensor_fit == 'AUTO':
            if pixel_aspect_x * resolution_x_in_px >= pixel_aspect_y * resolution_y_in_px:
                sensor_fit = 'HORIZONTAL'
            else:
                sensor_fit = 'VERTICAL'
        else:
            sensor_fit = cam.sensor_fit

        # Based on the sensor fit mode, determine the view in pixels
        pixel_aspect_ratio = pixel_aspect_y / pixel_aspect_x
        if sensor_fit == 'HORIZONTAL':
            view_fac_in_px = resolution_x_in_px
        else:
            view_fac_in_px = pixel_aspect_ratio * resolution_y_in_px

        return view_fac_in_px

    @staticmethod
    def get_intrinsics_as_K_matrix() -> np.ndarray:
        """ Returns the current set intrinsics in the form of a K matrix.

        This is basically the inverse of the the set_intrinsics_from_K_matrix() function.

        :return: The 3x3 K matrix
        """
        cam_ob = bpy.context.scene.camera
        cam = cam_ob.data

        f_in_mm = cam.lens
        resolution_x_in_px = bpy.context.scene.render.resolution_x
        resolution_y_in_px = bpy.context.scene.render.resolution_y

        # Compute sensor size in mm and view in px
        pixel_aspect_ratio = bpy.context.scene.render.pixel_aspect_y / bpy.context.scene.render.pixel_aspect_x
        view_fac_in_px = CameraUtility.get_view_fac_in_px(cam, bpy.context.scene.render.pixel_aspect_x, bpy.context.scene.render.pixel_aspect_y, resolution_x_in_px, resolution_y_in_px)
        sensor_size_in_mm = CameraUtility.get_sensor_size(cam)

        # Convert focal length in mm to focal length in px
        fx = f_in_mm / sensor_size_in_mm * view_fac_in_px
        fy = fx / pixel_aspect_ratio

        # Convert principal point in blenders format to px
        cx = (resolution_x_in_px - 1) / 2 - cam.shift_x * view_fac_in_px
        cy = (resolution_y_in_px - 1) / 2 + cam.shift_y * view_fac_in_px / pixel_aspect_ratio

        # Build K matrix
        K = np.array([[fx, 0, cx],
                      [0, fy, cy],
                      [0, 0, 1]])
        return K

    @staticmethod
    def get_fov() -> Tuple[float, float]:
        """ Returns the horizontal and vertical FOV of the current camera.

        Blender also offers the current FOV as direct attributes of the camera object, however
        at least the vertical FOV heavily differs from how it would usually be defined.

        :return: The horizontal and vertical FOV in radians.
        """
        # Get focal length
        K = CameraUtility.get_intrinsics_as_K_matrix()
        # Convert focal length to FOV
        fov_x = 2 * np.arctan(bpy.context.scene.render.resolution_x / 2 / K[0, 0])
        fov_y = 2 * np.arctan(bpy.context.scene.render.resolution_y / 2 / K[1, 1])
        return fov_x, fov_y

    @staticmethod
    def add_depth_of_field(camera: bpy.types.Camera, focal_point_obj: bpy.types.Object, fstop_value: float,
                           aperture_blades: int = 0, aperture_rotation: float = 0.0, aperture_ratio: float = 1.0,
                           focal_distance: float = -1.0):
        """
        Adds depth of field to the given camera, the focal point will be set by the focal_point_obj, ideally an empty
        instance is used for this see `MeshObject.create_empty()` on how to init one of those. A higher fstop value
        makes the resulting image look sharper, while a low value decreases the sharpness.

        Check the documentation on
        https://docs.blender.org/manual/en/latest/render/cameras.html#depth-of-field

        :param camera: The camera, which will get a depth of field added
        :param focal_point_obj: The used focal point, if the object moves the focal point will move with it
        :param fstop_value: A higher fstop value, will increase the sharpness of the scene
        :param aperture_blades: Amount of blades used in the camera
        :param aperture_rotation: Rotation of the blades in the camera in radiant
        :param aperture_ratio: Ratio of the anamorphic bokeh effect, below 1.0 will give a horizontal one, above one a \
                               vertical one.
        :param focal_distance: Sets the distance to the focal point when no focal_point_obj is given.
        """
        # activate depth of field rendering for this cameraera
        camera.dof.use_dof = True
        if focal_point_obj is not None:
            # set the focus point of the cameraera
            camera.dof.focus_object = focal_point_obj
        elif focal_distance >= 0.0:
            camera.dof.focus_distance = focal_distance
        else:
            raise RuntimeError("Either a focal_point_obj have to be given or the focal_distance has to be higher "
                               "than zero.")
        # set the aperture of the camera, lower values make the scene more out of focus, higher values make them look
        # sharper
        camera.dof.aperture_fstop = fstop_value
        # set the amount of blades
        camera.dof.aperture_blades = aperture_blades
        # setting the rotation of the aperture in radiant
        camera.dof.aperture_rotation = aperture_rotation
        # Change the amount of distortion to simulate the anamorphic bokeh effect. A setting of 1.0 shows no
        # distortion, where a number below 1.0 will cause a horizontal distortion, and a higher number will
        # cause a vertical distortion.
        camera.dof.aperture_ratio = aperture_ratio

    @staticmethod
    def set_lens_distortion(k1: float, k2: float, k3: float, p1: float, p2: float):
        """
        MISSING
        :param k1:
        :param k2:
        :param k3:
        :param p1:
        :param p2:
        :return:
        """
        # save the original image resolution
        original_image_resolution = (bpy.context.scene.render.resolution_y, bpy.context.scene.render.resolution_x)
        # first we need to get the current K matrix
        camera_K_matrix = CameraUtility.get_intrinsics_as_K_matrix()
        fx, fy = camera_K_matrix[0][0], camera_K_matrix[1][1]
        cx, cy = camera_K_matrix[0][2], camera_K_matrix[1][2]

        # get the current desired resolution
        # TODO check how the pixel aspect has to be factored in!
        desired_dis_res = (bpy.context.scene.render.resolution_y, bpy.context.scene.render.resolution_x)
        # Get row,column image coordinates for all pixels for row-wise image flattening
        # The center of the upper-left pixel has coordinates [0,0] both in DLR CalDe and python/scipy
        row = np.repeat(np.arange(0, desired_dis_res[0]), desired_dis_res[1])
        column = np.tile(np.arange(0, desired_dis_res[1]), desired_dis_res[0])

        # P_und is the undistorted pinhole projection at z==1 of all image pixels
        P_und = np.linalg.inv(camera_K_matrix) @ np.vstack((column, row, np.ones(np.prod(desired_dis_res[:2]))))

        # Init dist at undist
        x = P_und[0, :]
        y = P_und[1, :]
        res = [1e3]
        it = 0
        factor = 1.0
        while res[-1] > 0.2:
            r2 = np.square(x) + np.square(y)
            radial_part = (1 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2)
            x_ = x * radial_part + 2 * p2 * x * y + p1 * (r2 + 2 * np.square(x))
            y_ = y * radial_part + 2 * p1 * x * y + p2 * (r2 + 2 * np.square(y))

            error = np.max(np.hypot(fx * (x_ - P_und[0, :]), fy * (y_ - P_und[1, :])))
            res.append(error)
            it += 1

            # Take action if the optimization stalls or gets unstable
            # (distortion models are tricky if badly parameterized, especially in outer regions)
            if (it > 1) and (res[-1] > res[-2] * .999):
                factor *= .5
                if it > 1e3:
                    raise Exception(
                        "The iterative distortion algorithm is unstable/stalled after 1000 iterations. STOP.")
                if error > 1e9:
                    raise Exception("The iterative distortion algorithm is unstable. STOP.")

            # update undistorted projection
            x = x - (x_ - P_und[0, :]) * factor
            y = y - (y_ - P_und[1, :]) * factor

        # u and v are now the pixel coordinates on the undistorted image that
        # will distort into the row,column coordinates of the distorted image
        u = (fx * x + cx)
        v = (fy * y + cy)

        # Stacking this way for the interpolation in the undistorted image array
        mapping_coords = np.vstack([v, u])

        # Find out the resolution needed at the original image to generate filled-in distorted images
        min_und_column_needed = np.sign(np.min(u)) * np.ceil(np.abs(np.min(u)))
        max_und_column_needed = np.sign(np.max(u)) * np.ceil(np.abs(np.max(u)))
        min_und_row_needed = np.sign(np.min(v)) * np.ceil(np.abs(np.min(v)))
        max_und_row_needed = np.sign(np.max(v)) * np.ceil(np.abs(np.max(v)))
        columns_needed = max_und_column_needed - (min_und_column_needed - 1)
        rows_needed = max_und_row_needed - (min_und_row_needed - 1)
        cx_new = cx - (min_und_column_needed - 1) + 1
        cy_new = cy - (min_und_row_needed - 1) + 1
        # newly suggested resolution
        new_image_resolution = np.array([columns_needed, rows_needed])
        # To avoid spline boundary approximations at the border pixels ('mode' in map_coordinates() )
        new_image_resolution += 2

        # Adapt/shift the mapping function coordinates to the new_image_resolution resolution
        # (if we didn't, the mapping would only be valid for same resolution mapping)
        # (same resolution mapping yields undesired void image areas)
        # (this can in theory be performed in init_distortion() if we're positive about the resolution used)
        mapping_coords[0, :] += cy_new - cy
        mapping_coords[1, :] += cx_new - cx

        camera_changed_K_matrix = CameraUtility.get_intrinsics_as_K_matrix()
        # update cx and cy in the K matrix
        camera_changed_K_matrix[0, 2] = cx_new
        camera_changed_K_matrix[1, 2] = cy_new

        # reuse the values, which have been set before
        clip_start = bpy.context.scene.camera.data.clip_start
        clip_end = bpy.context.scene.camera.data.clip_end

        CameraUtility.set_intrinsics_from_K_matrix(camera_changed_K_matrix, new_image_resolution[0],
                                                   new_image_resolution[1], clip_start, clip_end)
        GlobalStorage.set("_lens_distortion_is_used", {"mapping_coords": mapping_coords,
                                                       "original_image_res": original_image_resolution})
