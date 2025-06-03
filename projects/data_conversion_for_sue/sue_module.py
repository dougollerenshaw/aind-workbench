"""
This module comes directly from Sue's repo here:
https://github.com/AllenNeuralDynamics/aind_su_etal_2022_conversion/blob/main/utils/behavior/session_utils.py

I just copied it here for context.
"""

import numpy as np
import os
import scipy.stats as stats
from collections import defaultdict
from typing import List, Dict, Any
from sklearn.linear_model import LogisticRegression

import os
import re
import numpy as np
import pandas as pd
from scipy.stats import zscore
from utils.basics.data_org import curr_computer, parse_session_string
import matplotlib.pyplot as plt
from scipy.io import loadmat
from itertools import chain
from scipy.stats import zscore
from scipy.stats import mode


def beh_analysis_no_plot(
    session_name,
    rev_for_flag=0,
    make_fig_flag=0,
    t_max=10,
    time_max=61000,
    time_bins=6,
    simple_flag=True,
):
    """
    Behavioral analysis function without plotting.

    Parameters:
        session_name (str): Session name.
        rev_for_flag (int, optional): Reverse format flag. Default is 0.
        make_fig_flag (int, optional): Flag to make figures. Default is 0.
        t_max (int, optional): Max trial bins. Default is 10.
        time_max (int, optional): Max time for binning. Default is 61000.
        time_bins (int, optional): Number of time bins. Default is 6.
        simple_flag (int, optional): Whether to return simple outputs. Default is 0.

    Returns:
        dict: Behavioral analysis results.
    """

    # Compute bin size and edges
    bin_size = (time_max - 1000) / time_bins
    time_bin_edges = np.arange(1000, time_max, bin_size)
    t_max = len(time_bin_edges) - 1

    # Get system-specific root path
    root = curr_computer()

    beh_session_data, licksL, licksR = load_session_df(session_name)

    # Process trials with responses
    response_inds = [
        i for i, x in enumerate(beh_session_data["rewardTime"]) if not np.isnan(x)
    ]
    rwd_delay, _ = mode(
        beh_session_data.loc[response_inds, "rewardTime"].values
        - beh_session_data.loc[response_inds, "respondTime"].values,
        keepdims=False,
    )

    all_reward_r = beh_session_data.loc[response_inds, "rewardR"].values
    all_reward_l = beh_session_data.loc[response_inds, "rewardL"].values

    all_choices = np.full(len(response_inds), np.nan)
    all_choices[~np.isnan(all_reward_r)] = 1
    all_choices[~np.isnan(all_reward_l)] = -1
    change_choice = np.insert(np.abs(np.diff(all_choices)) > 0, 0, False)
    all_reward_r[np.isnan(all_reward_r)] = 0
    all_reward_l[np.isnan(all_reward_l)] = 0

    # all_choice_r = (all_choices == 1).astype(int)
    # all_choice_l = (all_choices == -1).astype(int)

    all_rewards = np.zeros(len(all_choices))
    all_rewards[all_reward_r.astype(bool)] = 1
    all_rewards[all_reward_l.astype(bool)] = -1
    all_rewards_binary = np.where(all_rewards == -1, 1, all_rewards)
    # rewards_list = all_rewards[all_rewards != 0]

    all_no_rewards = np.copy(all_choices)
    all_no_rewards[all_rewards != 0] = 0

    # Compute inter-trial intervals
    time_btwn = np.diff(beh_session_data.loc[response_inds, "CSon"].values)
    time_btwn[time_btwn < 0] = 0
    time_btwn = np.insert(time_btwn, 0, np.nan)

    # Lick latencies

    # lick_side = np.full(len(response_inds), np.nan)
    # harvest_time = 1500
    # for i in response_inds:
    #     if not np.isnan(beh_session_data[i]["rewardTime"]):
    #         lick_lat.append(beh_session_data[i]["respondTime"] - beh_session_data[i]["CSon"])
    #         if not np.isnan(beh_session_data[i]["rewardL"]):
    #             lick_side[i] = -1
    #         elif not np.isnan(beh_session_data[i]["rewardR"]):
    #             lick_side[i] = 1

    lick_lat = (
        beh_session_data.loc[response_inds, "respondTime"].values
        - beh_session_data.loc[response_inds, "CSon"].values
    )
    # Z-score lick latencies
    real_id = np.array(lick_lat) > 50
    lick_lat_z = np.full(len(all_choices), np.nan)
    lick_lat_log = np.log(lick_lat)
    lick_lat_log_z = np.full(len(lick_lat), np.nan)

    inds_r = (all_choices == 1) & real_id
    inds_l = (all_choices == -1) & real_id
    lick_lat_z[inds_r] = zscore(np.array(lick_lat)[inds_r])
    lick_lat_z[inds_l] = zscore(np.array(lick_lat)[inds_l])
    lick_lat_log_z[inds_r] = zscore(lick_lat_log[inds_r])
    lick_lat_log_z[inds_l] = zscore(lick_lat_log[inds_l])

    # CS+ and CS- trials
    csplus_inds = [
        i for i, x in enumerate(beh_session_data["trialType"]) if x == "CSplus"
    ]
    csminus_inds = [
        i for i, x in enumerate(beh_session_data["trialType"]) if x == "CSminus"
    ]

    # Compute laser stimulation
    if "laser" in beh_session_data:
        laser = beh_session_data.loc[response_inds, "laser"].values
    else:
        laser = np.zeros(len(response_inds))

    # Store results in a dictionary
    results = {
        "allChoices": all_choices,
        "allRewards": all_rewards,
        "allRewardsBinary": all_rewards_binary,
        "allNoRewards": all_no_rewards,
        "lickLat": lick_lat,
        "lickLatInds": np.where(real_id)[0],
        "responseInds": response_inds,
        "lickLatZ": lick_lat_z,
        "lickLatLogZ": lick_lat_log_z,
        "CSplus": csplus_inds,
        "CSminus": csminus_inds,
        "rwdDelay": rwd_delay,
        "timeBtwn": time_btwn,
        # "lickSide": lick_side,
        "laser": laser,
        "svs": change_choice,
    }

    if simple_flag:
        return results


def load_df_from_mat(file_path):
    # initialization
    beh_df = pd.DataFrame()
    licks_L = []
    licks_R = []
    # Load the .mat file
    mat_data = loadmat(file_path)

    # Access the 'beh' struct
    if "behSessionData" in mat_data:
        beh = mat_data["behSessionData"]
    elif "sessionData" in mat_data:
        beh = mat_data["sessionData"]
    else:
        print("No 'behSessionData' or 'sessionData' found in the .mat file.")

    # Convert the struct fields to a dictionary
    # Assuming 'beh' is a MATLAB struct with fields accessible via numpy record arrays
    if isinstance(beh, np.ndarray) and beh.dtype.names is not None:
        beh_dict = {field: beh[field].squeeze() for field in beh.dtype.names}

        # Create a DataFrame from the dictionary
        beh_df = pd.DataFrame(beh_dict)
        beh_df.head(10)
        # for column in beh_df.columns:
        #     if beh_df[column].dtype == np.object:
        #         beh_df[column] = beh_df[column].str[0]
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
        # all licks
        licks_L = list(chain.from_iterable(beh_df["licksL"].tolist()))
        licks_R = list(chain.from_iterable(beh_df["licksR"].tolist()))

        list_to_drop = ["licksL", "licksR", "allLicks", "allSpikes"]
        unit_list = [x for x in beh_df.columns if "TT" in x]
        list_to_drop.extend(unit_list)

        beh_df.drop(list_to_drop, axis=1, inplace=True, errors="ignore")

    else:
        print("'beh' is not a struct or has unexpected format.")

    return beh_df, licks_L, licks_R


def load_session_df(session):
    """
    Load the session data from the .mat file.

    Args:
        session (str): The session name, e.g., 'mBB041d20161006'

    Returns:
        pd.DataFrame: The session data.
    """
    path_data = parse_session_string(session)
    session_df, licks_L, licks_R = load_df_from_mat(
        os.path.join(path_data["sortedFolder"], f"{session}_sessionData_behav.mat")
    )
    return session_df, licks_L, licks_R
