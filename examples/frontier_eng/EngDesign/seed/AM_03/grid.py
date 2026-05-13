import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.animation as animation

class Grid:
    def __init__(self, robot_trajectory, grid_size = 30, time_steps = 30, pedestrian_size = 2):
        self.grid_size = grid_size
        self.time_steps = time_steps
        self.pedestrian_size = pedestrian_size
    
        # Define large static boxes (maze-like)
        self.static_boxes = [
            ((5, 0), (7, 15)),      # Vertical wall
            ((10,20), (20,30)),     # Top Squre
            ((15, 5), (30, 10))      # Horizontal wall
        ]

        # Define pedestrian movement paths (t, x, y)
        self.pedestrian_paths = {
            'ped1': [   (0,1,1),
                        (1,1,2),
                        (2,1,4),
                        (3,1,6),
                        (4,1,7),
                        (5,1,9),
                        (6,1,11),
                        (7,2,13),
                        (8,2,14),
                        (9,3,16),
                        (10,6,16),
                        (11,7,15),
                        (12,8,13),
                        (13,9,12),
                        (14,10,11),
                        (15,11,11),
                        (16,12,11),
                        (17,13,11),
                        (18,14,11),
                        (19,15,11),
                        (20,16,11),
                        (21,17,11),
                        (22,18,11),
                        (23,19,11),
                        (24,20,11),
                        (25,21,11),
                        (26,22,11),
                        (27,23,11),
                        (28,24,11),
                        (29,25,11)
                    ],  
            'ped2': [   (0,25,28),
                        (1,25,28),
                        (2,25,26),
                        (3,25,24),
                        (4,25,22),
                        (5,25,20),
                        (6,25,18),
                        (7,25,16),
                        (8,25,14),
                        (9,24,12),
                        (10,22,12),
                        (11,20,12),
                        (12,19,12),
                        (13,17,12),
                        (14,16,12),
                        (15,16,12),
                        (16,15,13),
                        (17,14,15),
                        (18,12,16),
                        (19,10,16),
                        (20,8,16),
                        (21,6,16),
                        (22,5,16),
                        (23,4,16),
                        (24,4,17),
                        (25,4,18),
                        (26,4,19),
                        (27,4,20),
                        (28,4,21),
                        (29,4,22)
                    ], 
            'ped3': [   (0, 25, 2),
                        (1, 24, 2),
                        (2, 23, 2),
                        (3, 22, 2),
                        (4, 21, 2),
                        (5, 20, 2),
                        (6, 19, 2),
                        (7, 18, 2),
                        (8, 17, 2),
                        (9, 16, 2),
                        (10,15,2),
                        (11,14,2),
                        (12,13,2),
                        (13,12,2),
                        (14,11,2),
                        (15,10,2),
                        (16,9,3),
                        (17,8,4),
                        (18,8,6),
                        (19,8,8),
                        (20,8,10),
                        (21,8,12),
                        (22,8,14),
                        (23,8,16),
                        (24,8,18),
                        (25,8,20),
                        (26,8,22),
                        (27,8,24),
                        (28,8,26),
                        (29,8,28)
                    ],
            "robot": robot_trajectory
        }
        self.fig, self.ax = plt.subplots(figsize=(6, 6))
        self.trails = {key: [] for key in self.pedestrian_paths}

    def check_obstacle_collision(self):
        # Check if the pedestrian collides with any static boxes
        num_collisions = 0
        for t in self.pedestrian_paths['robot']:
            _, x, y = t
            for (ox1, oy1), (ox2, oy2) in self.static_boxes:
                if not (x + self.pedestrian_size <= ox1 
                        or x >= ox2 
                        or y + self.pedestrian_size <= oy1 
                        or y >= oy2):
                    num_collisions += 1
        return num_collisions 

    def check_pedestrian_collision(self):
        size = self.pedestrian_size
        num_collisions = 0
        for tuple in self.pedestrian_paths['robot']:
            t, x1, y1 = tuple
            for pedestrian_id, path in self.pedestrian_paths.items():
                if pedestrian_id == 'robot':
                    continue
                x2, y2 = path[t][1], path[t][2]
                # Check if the pedestrian collides with the robot
                if not (x1 + size <= x2 or x2 + size <= x1 or
                    y1 + size <= y2 or y2 + size <= y1):
                    num_collisions += 1

        return num_collisions

    def over_speed_limit(self, speed_limit = 2):
        # Check if the robot exceeds the speed limit
        for i in range(1, len(self.pedestrian_paths['robot'])):
            t1, x1, y1 = self.pedestrian_paths['robot'][i-1]
            t2, x2, y2 = self.pedestrian_paths['robot'][i]
            if abs(x1 - x2) > speed_limit or abs(y1 - y2) > speed_limit:
                return True
        return False
    
    def hits_goal(self, goal):
        for t, x, y in self.pedestrian_paths['robot']:
            if (x, y) == goal:
                return True
        return False
    
    def draw_frame(self,t):
        # Initialize trails
        self.ax.clear()
        self.ax.set_xlim(0, self.grid_size)
        self.ax.set_ylim(0, self.grid_size)
        self.ax.set_xticks(range(0, self.grid_size + 1, 5))
        self.ax.set_yticks(range(0, self.grid_size + 1, 5))
        self.ax.grid(True)
        self.ax.set_title(f"Time: {t} seconds")

        # Draw static maze boxes
        for (x1, y1), (x2, y2) in self.static_boxes:
            self.ax.add_patch(patches.Rectangle((x1, y1), x2 - x1, y2 - y1, color='gray'))

        # Draw pedestrians with trails and collision check
        colors = ['blue', 'green', 'yellow', "purple"]
        for idx, (ped_id, path) in enumerate(self.pedestrian_paths.items()):
            # Get latest position at or before time t
            past_positions = [(pt, x, y) for pt, x, y in path if pt <= t]
            if past_positions:
                _, x, y = past_positions[-1]
                self.trails[ped_id].append((x, y))

                # Draw current position
                self.ax.add_patch(patches.Rectangle((x, y), self.pedestrian_size, self.pedestrian_size, color=colors[idx]))

                # Draw trail
                for px, py in self.trails[ped_id][:-1]:
                    self.ax.add_patch(patches.Rectangle((px, py), self.pedestrian_size, self.pedestrian_size,
                                                edgecolor=colors[idx], facecolor='none',
                                                linestyle='--', linewidth=1))

    def save_animation(self):
        # Create animation
        ani = animation.FuncAnimation(self.fig, self.draw_frame, frames=self.time_steps, interval=500, repeat=False)

        # Save animation
        ani.save("pedestrian_maze_animation.mp4")

if __name__ == "__main__":
    # Example robot trajectory
    robot_trajectory = [
        (0, 17, 2),
        (1, 15, 2),
        (2, 13, 2),
        (3, 11, 2),
        (4, 10, 4),
        (5, 10, 6),
        (6, 10, 8),
        (7, 10, 9),
        (8, 10, 10),
        (9, 10, 11),
        (10, 10, 12),
        (11, 10, 13),
        (12, 10, 14),
        (13, 9, 15),
        (14, 8, 16),
        (15, 7, 17),
        (16, 6, 18),
        (17, 5, 20),
        (18, 7, 18),
        (19, 7, 18),
        (20, 7, 18),
        (21, 9, 18),
        (22, 11, 16),
        (23, 13, 16),
        (24, 15, 16),
        (25, 17, 18),
        (26, 19, 18),
        (27, 21, 20),
        (28, 23, 22),
        (29, 25, 24)
    ]
    grid = Grid(robot_trajectory)
    num_obs_collisions = grid.check_obstacle_collision()
    num_ped_collisions = grid.check_pedestrian_collision()
    speed_limit_exceeded = grid.over_speed_limit()
    print("Number of obstacle collisions:", num_obs_collisions)
    print("Number of pedestrian collisions:", num_ped_collisions)
    print("Speed limit exceeded:", speed_limit_exceeded)
    print("Hits Goal A:", grid.hits_goal((5, 20)))
    print("Hits Goal B:", grid.hits_goal((25, 24)))
    grid.save_animation()