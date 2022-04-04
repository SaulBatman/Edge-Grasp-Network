import numpy as np
import torch
import mayavi.mlab as mlab
import sample
import trimesh
from dataset_pyg import Grasp_Dataset,GraspNormalization
from transform import Transform,Rotation

def get_control_point_tensor(batch_size, use_tensor=False):
    """
      Outputs a tensor of shape (batch_size x 6 x 3).
      use_tf: switches between outputing a tensor and outputing a numpy array.
    """
    control_points = np.load('./panda.npy')[:, :3]
    control_points = [[0, 0, 0], [0, 0, 0], control_points[0, :],
                      control_points[1, :], control_points[-2, :], control_points[-1, :]]
    control_points = np.asarray(control_points, dtype=np.float32)
    control_points = np.tile(
        np.expand_dims(
            control_points, 0), [
            batch_size, 1, 1])
    if use_tensor:
        return torch.from_numpy(control_points)
    return control_points

def get_color_plasma_org(x):
    import matplotlib.pyplot as plt
    return tuple([x for i, x in enumerate(plt.cm.plasma(x)) if i < 3])

def get_color_plasma(x):
    return tuple([float(1 - x), float(x) , float(0)])

def plot_mesh(mesh):
    assert type(mesh) == trimesh.base.Trimesh
    mlab.triangular_mesh (
        mesh.vertices[:, 0],
        mesh.vertices[:, 1],
        mesh.vertices[:, 2],
        mesh.faces,
        colormap='Blues'
    )


def draw_scene(
        pc,
        grasps=[],
        grasp_scores=None,
        grasp_color=None,
        gripper_color=(0, 1, 0),
        mesh=None,
        show_gripper_mesh=False,
        grasps_selection=None,
        visualize_diverse_grasps=False,
        min_seperation_distance=0.03,
        pc_color=None,
        plasma_coloring=False,):
    """
    Draws the 3D scene for the object and the scene.
    Args:
      pc: point cloud of the object
      grasps: list of 4x4 numpy array indicating the transformation of the grasps.
        grasp_scores: grasps will be colored based on the scores. If left
        empty, grasps are visualized in green.
      grasp_color: if it is a tuple, sets the color for all the grasps. If list
        is provided it is the list of tuple(r,g,b) for each grasp.
      mesh: If not None, shows the mesh of the object. Type should be trimesh
         mesh.
      show_gripper_mesh: If True, shows the gripper mesh for each grasp.
      grasp_selection: if provided, filters the grasps based on the value of
        each selection. 1 means select ith grasp. 0 means exclude the grasp.
      visualize_diverse_grasps: sorts the grasps based on score. Selects the
        top score grasp to visualize and then choose grasps that are not within
        min_seperation_distance distance of any of the previously selected
        grasps. Only set it to True to declutter the grasps for better
        visualization.
      pc_color: if provided, should be a n x 3 numpy array for color of each
        point in the point cloud pc. Each number should be between 0 and 1.
      plasma_coloring: If True, sets the plasma colormap for visualizting the
        pc.
    """

    max_grasps = 200
    grasps = np.array(grasps)

    if grasp_scores is not None:
        grasp_scores = np.array(grasp_scores)

    if len(grasps) > max_grasps:

        print('Downsampling grasps, there are too many')
        chosen_ones = np.random.randint(low=0, high=len(grasps), size=max_grasps)
        grasps = grasps[chosen_ones]
        if grasp_scores is not None:
            grasp_scores = grasp_scores[chosen_ones]

    if mesh is not None:
        if type(mesh) == list:
            for elem in mesh:
                plot_mesh(elem)
        else:
            plot_mesh(mesh)

    if pc_color is None and pc is not None:
        if plasma_coloring:
            mlab.points3d(pc[:, 0], pc[:, 1], pc[:, 2], pc[:, 2], colormap='plasma')
        else:
            mlab.points3d(pc[:, 0], pc[:, 1], pc[:, 2], color=(0.1,0.1,1), scale_factor=0.001)
    elif pc is not None:
        if plasma_coloring:
            mlab.points3d(pc[:, 0], pc[:, 1], pc[:, 2], pc_color[:, 0], colormap='plasma')
        else:
            #print(pc_color)
            rgba = np.zeros((pc.shape[0], 4), dtype=np.uint8)
            rgba[:, :3] = np.asarray(pc_color)*255
            rgba[:, 3] = 255
            #print(rgba)
            src = mlab.pipeline.scalar_scatter(pc[:, 0], pc[:, 1], pc[:, 2])
            src.add_attribute(rgba, 'colors')
            src.data.point_data.set_active_scalars('colors')
            g = mlab.pipeline.glyph(src)
            g.glyph.scale_mode = "data_scaling_off"
            g.glyph.glyph.scale_factor = 0.001

    grasp_pc = np.squeeze(get_control_point_tensor(1, False), 0)
    print(grasp_pc.shape)
    grasp_pc[2, 2] = 0.059
    grasp_pc[3, 2] = 0.059

    mid_point = 0.5 * (grasp_pc[2, :] + grasp_pc[3, :])

    modified_grasp_pc = []
    modified_grasp_pc.append(np.zeros((3,), np.float32))
    modified_grasp_pc.append(mid_point)
    modified_grasp_pc.append(grasp_pc[2])
    modified_grasp_pc.append(grasp_pc[4])
    modified_grasp_pc.append(grasp_pc[2])
    modified_grasp_pc.append(grasp_pc[3])
    modified_grasp_pc.append(grasp_pc[5])

    grasp_pc = np.asarray(modified_grasp_pc)

    def transform_grasp_pc(g):
        output = np.matmul(grasp_pc, g[:3, :3].T)
        output += np.expand_dims(g[:3, 3], 0)

        return output

    if grasp_scores is not None:
        indexes = np.argsort(-np.asarray(grasp_scores))
    else:
        indexes = range(len(grasps))

    print('draw scene ', len(grasps))

    selected_grasps_so_far = []
    removed = 0

    if grasp_scores is not None:
        min_score = np.min(grasp_scores)
        max_score = np.max(grasp_scores)
        top5 = np.array(grasp_scores).argsort()[-5:][::-1]
        #print(grasp_scores)
    for ii in range(len(grasps)):
        i = indexes[ii]
        if grasps_selection is not None:
            if grasps_selection[i] == False:
                continue

        g = grasps[i]
        is_diverse = True
        for prevg in selected_grasps_so_far:
            distance = np.linalg.norm(prevg[:3, 3] - g[:3, 3])

            if distance < min_seperation_distance:
                is_diverse = False
                break

        if visualize_diverse_grasps:
            if not is_diverse:
                removed += 1
                continue
            else:
                if grasp_scores is not None:
                    print('selected', i, grasp_scores[i], min_score, max_score)
                else:
                    print('selected', i)
                selected_grasps_so_far.append(g)

        if isinstance(gripper_color, list):
            pass
        elif grasp_scores is not None:
            normalized_score = (grasp_scores[i] - min_score) / (max_score - min_score + 0.0001)
            if grasp_color is not None:
                gripper_color = grasp_color[ii]
            else:
                gripper_color = get_color_plasma(normalized_score)
            if min_score == 1.0:
                gripper_color = (0.0, 1.0, 0.0)

        if show_gripper_mesh:
            gripper_mesh = sample.Object('panda_gripper.obj').mesh
            gripper_mesh.apply_transform(g)
            mlab.triangular_mesh(
                gripper_mesh.vertices[:, 0],
                gripper_mesh.vertices[:, 1],
                gripper_mesh.vertices[:, 2],
                gripper_mesh.faces,
                color=gripper_color,
                opacity=1 if visualize_diverse_grasps else 0.5
            )
        else:
            pts = np.matmul(grasp_pc, g[:3, :3].T)
            pts += np.expand_dims(g[:3, 3], 0)
            if isinstance(gripper_color, list):
                mlab.plot3d(pts[:, 0], pts[:, 1], pts[:, 2], color=gripper_color[i], tube_radius=0.003, opacity=1)
            else:
                tube_radius = 0.001
                mlab.plot3d(pts[:, 0], pts[:, 1], pts[:, 2], color=gripper_color, tube_radius=tube_radius, opacity=1)

    print('removed {} similar grasps'.format(removed))


def get_axis():
    # hacky axis for mayavi
    axis = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    axis_x = np.array([np.linspace(0, 0.10, 50), np.zeros(50), np.zeros(50)]).T
    axis_y = np.array([np.zeros(50), np.linspace(0, 0.10, 50), np.zeros(50)]).T
    axis_z = np.array([np.zeros(50), np.zeros(50), np.linspace(0, 0.10, 50)]).T
    axis = np.concatenate([axis_x, axis_y, axis_z], axis=0)
    return axis


def vis_grasp_panda(data):
    pc = data.pos.numpy()
    orientation = data.orientation_gt[:, 0, :].numpy()
    position = data.position_gt.numpy()
    grasps_matrix1 = []
    pre_trans1 = Rotation.from_euler('z', np.pi / 2)
    pre_trans2 = Transform(Rotation.identity(), [0.0, 0.0, -0.037])
    for i in range(len(position)):
        rot = Rotation.from_quat(orientation[i, :]) * pre_trans1
        trans = position[i, :]
        grasp = Transform(rotation=rot, translation=trans)
        grasp = grasp * pre_trans2
        grasps_matrix1.append(grasp.as_matrix())
    draw_scene(pc,grasps_matrix1,show_gripper_mesh=False)
    mlab.show()



control_points = np.load('./panda.npy')
#make sure you have right root dir path below
dataset = Grasp_Dataset(root='./raw/foo',transform = GraspNormalization(),train=True)
for data in dataset:
    data = dataset[86]
    pc = data.pos.numpy()
    positive_index = data.positive_mask.numpy()
    # TODO change the color for positive and negative
    pc_colors = np.tile(np.asarray([[0.1, 0.1, 1.]]),(len(pc),1))
    pc_colors[positive_index,:] = np.asarray([0.1, 1, 0.1])
    print(pc_colors)
    # label = data.label
    # single_positive_mask = label==1
    # labels = data.labels[single_positive_mask]
    scores = data.labels.sum(dim=1)/9
    scores = scores.numpy()
    print(scores)
    negative_grasp_mask = scores==0
    print(negative_grasp_mask)
    orientation = data.orientation_gt[:,0,:].numpy()
    position = data.position_gt.numpy()
    grasps_matrix1 = []
    pre_trans1 = Rotation.from_euler('z', np.pi/2)
    pre_trans2 = Transform(Rotation.identity(), [0.0, 0.0, -0.037])
    for i in range(len(position)):
        rot = Rotation.from_quat(orientation[i,:])*pre_trans1
        trans = position[i,:]
        grasp = Transform(rotation=rot,translation=trans)
        grasp = grasp * pre_trans2
        grasps_matrix1.append(grasp.as_matrix())
    print(np.asarray(grasps_matrix1).shape)
    negative_grasp_matrix1 = np.asarray(grasps_matrix1)[negative_grasp_mask]
    grasp_negative_score = scores[negative_grasp_mask]
    print(negative_grasp_matrix1.shape,grasp_negative_score)
    #draw_scene(pc,negative_grasp_matrix1,show_gripper_mesh=False,grasp_scores=grasp_negative_score,visualize_diverse_grasps=False,pc_color=pc_colors)
    draw_scene(pc, grasps_matrix1, show_gripper_mesh=False, grasp_scores=scores,
               visualize_diverse_grasps=True, pc_color=pc_colors)
    mlab.show()
    break



# grasps_matrix2 = []
# #pre_trans = Rotation.from_euler('z', np.pi/2)
# for i in range(len(position)):
#     rot = Rotation.from_quat(orientation[i,:])
#     trans = position[i,:]
#     grasp = Transform(rotation=rot,translation=trans).as_matrix()
#     grasps_matrix2.append(grasp)
#
#
# grasps_matrix3 = []
# for i in range(len(position)):
#     rot = Rotation.from_quat(orientation[i,:])*pre_trans1
#     trans = position[i,:]
#     grasp = Transform(rotation=rot,translation=trans)
#     grasp = grasp
#     grasps_matrix3.append(grasp.as_matrix())

# draw_scene(pc,grasps_matrix1[:10],show_gripper_mesh=False)
# mlab.show()

# pc = np.array([[0,0,0],[0.1,0,0],[0,0,0.1]])
# grasps_matrix = [Transform(rotation=Rotation.identity(),translation=[0,0,0]).as_matrix()]
# print(grasps_matrix)
# draw_scene(pc,grasps_matrix,show_gripper_mesh=False)
# mlab.show()