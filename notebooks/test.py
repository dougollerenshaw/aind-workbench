from dynamic_foraging.contracts import dynamic_foraging_contract

# define the path to the data
path_to_data = "c:\some_folder_with_data\dynamic_foraging\todays_data"

# validate the data
dynamic_foraging_contract.validate(path_to_data)

# load the data
my_data = dynamic_foraging_contract.load(path_to_data)

# get the harp behavior data
harp_behavior_data = my_data.get("HarpBehavior")

# get the trial table as a pandas dataframe
trial_table = my_data.get("TrialTable")

# Now do some qc steps

# write out qc json