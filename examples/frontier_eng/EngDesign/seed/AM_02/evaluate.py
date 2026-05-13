from grid import Grid

def evaluate_llm_response(llm_response):
    try:
        robot_trajectory1 = llm_response.config.robot_trajectory1
        robot_trajectory2 = llm_response.config.robot_trajectory2

        robot_trajectory1 = [(item.t, item.x, item.y) for item in robot_trajectory1]
        robot_trajectory2 = [(item.t, item.x, item.y) for item in robot_trajectory2]

        # Check if the robot trajectory is a list of tuples with 3 integers
        if not isinstance(robot_trajectory1, list) \
            or not all(isinstance(item, tuple) \
            and len(item) == 3 \
            and all(isinstance(i, int) for i in item) for item in robot_trajectory1):
            return False, {"error": "Invalid robot trajectory format"}, None, None
        if not isinstance(robot_trajectory2, list) \
            or not all(isinstance(item, tuple) \
            and len(item) == 3 \
            and all(isinstance(i, int) for i in item) for item in robot_trajectory1):
            return False, {"error": "Invalid robot trajectory format"}, None, None
        
        details = dict()

        grid = Grid(robot_trajectory1, robot_trajectory2)
        score = 0
        for i in range(1,3):
            robot_name = f"robot{i}"
            num_obs_collisions = grid.check_obstacle_collision(robot_name)
            num_ped_collisions = grid.check_pedestrian_collision(robot_name)
            speed_limit_exceeded = grid.over_speed_limit(robot_name)
            if i == 1:
                start_correct = robot_trajectory1[0] == (0, 17, 2)
                end_correct = robot_trajectory1[-1] == (19, 5, 24)
            else:
                start_correct = robot_trajectory2[0] == (0, 5, 25)
                end_correct = robot_trajectory2[-1] == (19, 25, 25)

            if start_correct:
                score += 5
            if end_correct:
                score += 10
            if num_obs_collisions == 0:
                score += 12.5
            if num_ped_collisions == 0:
                score += 12.5
            if not speed_limit_exceeded:
                score += 10
            details[f"{robot_name}: Start position correct"] = start_correct
            details[f"{robot_name}: End position correct"] = end_correct
            details[f"{robot_name}: Number of collisions with static obstacles"] = num_obs_collisions
            details[f"{robot_name}: Number of collisions with walking pedestrians"] = num_ped_collisions
            details[f"{robot_name}: Over Speed limit"] = speed_limit_exceeded


        passed = (score == 100)

        confidence = 100

        grid.save_animation()

        return passed, details, score, confidence
    except Exception as e:
        # print(e)
        return False, {"error": str(e)}, None, None