import os
import numpy as np
import pandas as pd
from scipy.io import loadmat
from itertools import chain


def load_session_data(file_path):
    """
    Load the session data from the .mat file

    Args:
        file_path (str): The path to the .mat file.

    Returns:
        pd.DataFrame: The session data DataFrame.
        list: List of left licks (licks_L).
        list: List of right licks (licks_R).
    """
    beh_df = pd.DataFrame()
    licks_L = []
    licks_R = []
    mat_data = loadmat(file_path)
    if "behSessionData" in mat_data:
        beh = mat_data["behSessionData"]
    elif "sessionData" in mat_data:
        beh = mat_data["sessionData"]
    else:
        print("No 'behSessionData' or 'sessionData' found in the .mat file.")
        return beh_df, licks_L, licks_R
    if isinstance(beh, np.ndarray) and beh.dtype.names is not None:
        beh_dict = {field: beh[field].squeeze() for field in beh.dtype.names}
        beh_df = pd.DataFrame(beh_dict)
        for column in beh_df.columns:
            if column in [
                "trialEnd",
                "CSon",
                "respondTime",
                "rewardTime",
                "rewardProbL",
                "rewardProbR",
                "laser",
                "rewardL",
                "rewardR",
            ]:
                curr_list = beh_df[column].tolist()
                curr_list = [
                    (
                        np.float64(x[0][0])
                        if x.shape[0] > 0 and not np.isnan(x[0][0])
                        else np.nan
                    )
                    for x in curr_list
                ]
            elif column in ["licksL", "licksR", "trialType"]:
                curr_list = beh_df[column].tolist()
                curr_list = [x[0] if len(x) > 0 else x for x in curr_list]
            beh_df[column] = curr_list
        licks_L = list(chain.from_iterable(beh_df["licksL"].tolist()))
        licks_R = list(chain.from_iterable(beh_df["licksR"].tolist()))
        list_to_drop = ["licksL", "licksR", "allLicks", "allSpikes"]
        unit_list = [x for x in beh_df.columns if "TT" in x]
        list_to_drop.extend(unit_list)
        beh_df.drop(list_to_drop, axis=1, inplace=True, errors="ignore")
    else:
        print("'beh' is not a struct or has unexpected format.")
    return beh_df, licks_L, licks_R


def calculate_session_duration(beh_df):
    """
    Calculate the session duration in seconds as the difference between the largest and smallest timestamp
    across all time columns (trialEnd, CSon, respondTime, rewardTime).
    """
    time_cols = ["trialEnd", "CSon", "respondTime", "rewardTime"]
    all_times = []
    for col in time_cols:
        if col in beh_df:
            vals = beh_df[col].dropna().values
            all_times.extend(vals)
    if not all_times:
        return 0.0
    return (np.nanmax(all_times) - np.nanmin(all_times)) / 1000.0


def count_rewards(beh_df):
    """
    Count the total number of rewards actually delivered.
    Returns the count of rewardL=1.0 + rewardR=1.0 values.

    Note: rewardTime records when reward decisions were made (regardless of delivery),
    while rewardL/rewardR record actual delivery (1.0 = delivered, 0.0 = withheld due to probability).
    """
    rewardL_delivered = (
        (beh_df["rewardL"] == 1.0).sum() if "rewardL" in beh_df else 0
    )
    rewardR_delivered = (
        (beh_df["rewardR"] == 1.0).sum() if "rewardR" in beh_df else 0
    )
    total_rewards = rewardL_delivered + rewardR_delivered
    return total_rewards


def calculate_reward_volume_microliters(beh_df, volume_per_reward=3.0):
    """
    Calculate total reward volume consumed in microliters.

    Args:
        beh_df: Behavioral DataFrame
        volume_per_reward: Volume per reward in microliters (default: 3.0)

    Returns:
        float: Total volume in microliters
    """
    total_rewards = count_rewards(beh_df)
    return total_rewards * volume_per_reward


def extract_behavioral_metrics(
    beh_df, licks_L, licks_R, volume_per_reward=3.0
):
    """
    Extract behavioral metrics relevant to AIND data schema from session data.

    Args:
        beh_df: Behavioral DataFrame
        licks_L: List of left licks
        licks_R: List of right licks
        volume_per_reward: Volume per reward in microliters (default: 3.0)

    Returns:
        dict: Dictionary of behavioral metrics
    """
    metrics = {}

    # Basic session metrics
    metrics["session_duration_seconds"] = calculate_session_duration(beh_df)
    metrics["total_rewards"] = count_rewards(beh_df)
    metrics["reward_volume_microliters"] = calculate_reward_volume_microliters(
        beh_df, volume_per_reward
    )

    # Lick metrics
    metrics["total_left_licks"] = len(licks_L)
    metrics["total_right_licks"] = len(licks_R)
    metrics["total_licks"] = len(licks_L) + len(licks_R)

    # Trial metrics
    metrics["total_trials"] = len(beh_df) if not beh_df.empty else 0

    # Reward breakdown
    if "rewardL" in beh_df.columns:
        metrics["left_rewards"] = (beh_df["rewardL"] == 1.0).sum()
    else:
        metrics["left_rewards"] = 0

    if "rewardR" in beh_df.columns:
        metrics["right_rewards"] = (beh_df["rewardR"] == 1.0).sum()
    else:
        metrics["right_rewards"] = 0

    # Trial type breakdown (if available)
    if "trialType" in beh_df.columns:
        trial_types = beh_df["trialType"].value_counts().to_dict()
        for trial_type, count in trial_types.items():
            metrics[f"trial_type_{trial_type}_count"] = count

    return metrics


def construct_file_path(base_path, vast_path, session_name):
    """
    Construct the full file path to the behavioral data file.

    Args:
        base_path: Base path to data files
        vast_path: Path from the vast_path column
        session_name: Name of the session

    Returns:
        str: Full path to the .mat file
    """
    # Handle the fact that vast_path includes scratch/sueSu
    if vast_path.startswith("scratch/sueSu/"):
        relative_path = vast_path[len("scratch/sueSu/") :]
    else:
        relative_path = vast_path

    return os.path.join(
        base_path,
        relative_path,
        "sorted",
        "session",
        f"{session_name}_sessionData_behav.mat",
    )
