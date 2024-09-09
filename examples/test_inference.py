import cv2
import jax
import tensorflow_datasets as tfds
import tqdm
import numpy as np

# path_finetuned = "/home/aalto-robotics/checkpoints/"
# path_data = "/home/aalto-robotics/Xiwei/rlds_dataset_builder/test_tfds_build/rosdata/example_dataset/1.0.0"
path_finetuned = "/scratch/work/zhaox9/finetuned_checkpoints/isaacsim_checkpoints/"
path_data = "/scratch/work/zhaox9/rlds_dataset_builder_own/tfds_build/rosdata/example_dataset/1.0.0"

from octo.model.octo_model import OctoModel
## load fine-tuned model
model = OctoModel.load_pretrained(path_finetuned)

## load test data
# create RLDS dataset builder
builder = tfds.builder_from_directory(builder_dir=path_data)
ds = builder.as_dataset(split='train[:1]')

# sample episode + resize to 256x256 (default third-person cam resolution)
episode = next(iter(ds))
steps = list(episode['steps'])
images = [cv2.resize(np.array(step['observation']['image']), (256, 256)) for step in steps]
images_wrist = [np.array(step['observation']['wrist_image']) for step in steps]

# extract goal image & language instruction
goal_image = images[-1]
language_instruction = steps[0]['language_instruction'].numpy().decode()

# visualize episode
print(f'Instruction: {language_instruction}')
print(f'Dataset loaded!')

WINDOW_SIZE = 2

## create `task` dict
task = model.create_tasks(goals={"image_primary": goal_image[None]})   # for goal-conditioned
task = model.create_tasks(texts=[language_instruction])                  # for language conditioned

# run inference loop, this model only uses 3rd person image observations for bridge
# collect predicted and true actions
pred_actions, true_actions = [], []
for step in tqdm.trange(len(images) - (WINDOW_SIZE - 1)):
    input_images = np.stack(images[step:step+WINDOW_SIZE])[None]
    input_images_wrist = np.stack(images_wrist[step:step+WINDOW_SIZE])[None]
    observation = {
        'image_primary': input_images,
        'image_wrist': input_images_wrist,
        'timestep_pad_mask': np.full((1, input_images.shape[1]), True, dtype=bool)
    }
    
    # this returns *normalized* actions --> we need to unnormalize using the dataset statistics
    actions = model.sample_actions(
        observation, 
        task, 
        # unnormalization_statistics=model.dataset_statistics["bridge_dataset"]["action"], 
        rng=jax.random.PRNGKey(0)
    )
    actions = actions[0] # remove batch dim

    pred_actions.append(actions)
    final_window_step = step + WINDOW_SIZE - 1
    true_actions.append(
        steps[final_window_step]['action']
    )

## compute L1 loss between predicted and true actions
l1_loss = np.mean(np.abs(np.stack(pred_actions) - np.stack(true_actions)))
print(f'L1 loss: {l1_loss}')

## visualize predicted actions
import matplotlib.pyplot as plt

ACTION_DIM_LABELS = ['x', 'y', 'z', 'yaw', 'pitch', 'roll', 'grasp', "aa", "bb"]

# build image strip to show above actions
img_strip = np.concatenate(np.array(images[::3]), axis=1)

# set up plt figure
figure_layout = [
    ['image'] * len(ACTION_DIM_LABELS),
    ACTION_DIM_LABELS
]
plt.rcParams.update({'font.size': 12})
fig, axs = plt.subplot_mosaic(figure_layout)
fig.set_size_inches([45, 10])

# # plot actions
# pred_actions = np.array(pred_actions).squeeze()
# true_actions = np.array(true_actions).squeeze()
# for action_dim, action_label in enumerate(ACTION_DIM_LABELS):
#   # actions have batch, horizon, dim, in this example we just take the first action for simplicity
#   axs[action_label].plot(pred_actions[:, 0, action_dim], label='predicted action')
#   axs[action_label].plot(true_actions[:, action_dim], label='ground truth')
#   axs[action_label].set_title(action_label)
#   axs[action_label].set_xlabel('Time in one episode')

# axs['image'].imshow(img_strip)
# axs['image'].set_xlabel('Time in one episode (subsampled)')
# plt.legend()
# plt.show()


