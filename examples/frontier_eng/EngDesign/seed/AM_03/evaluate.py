from grid import Grid

def evaluate_llm_response(llm_response):
    try:
        robot_trajectory = llm_response.config.robot_trajectory
        robot_trajectory = [(item.t, item.x, item.y) for item in robot_trajectory]
        
        # Check if the robot trajectory is a list of tuples with 3 integers
        if not isinstance(robot_trajectory, list) \
            or not all(isinstance(item, tuple) \
            and len(item) == 3 \
            and all(isinstance(i, int) for i in item) for item in robot_trajectory):

            return False, {"error": "Invalid robot trajectory format"}, None, None

        grid = Grid(robot_trajectory)
        num_obs_collisions = grid.check_obstacle_collision()
        num_ped_collisions = grid.check_pedestrian_collision()
        speed_limit_exceeded = grid.over_speed_limit()
        start_correct = robot_trajectory[0] == (0, 17, 2)
        hits_goal_A = grid.hits_goal((5, 20))
        hits_goal_B = grid.hits_goal((25, 24))

        score = 0
        if start_correct:
            score += 10
        if hits_goal_A:
            score += 10
        if hits_goal_B:
            score += 10
        if num_obs_collisions == 0:
            score += 25
        if num_ped_collisions == 0:
            score += 25
        if not speed_limit_exceeded:
            score += 20

        passed = (score == 100)

        details = {"Start position correct": start_correct, 
                   "Hit Goal A": hits_goal_A, 
                   "Hit Goal B": hits_goal_B,
                   "Number of collisions with static obstacles": num_obs_collisions, 
                   "Number of collisions with walking pedestrians": num_ped_collisions, 
                   "Over Speed limit": speed_limit_exceeded}

        confidence = 100

        grid.save_animation()

        return passed, details, score, confidence
    except Exception as e:
        # print(e)
        return False, {"error": str(e)}, None, None