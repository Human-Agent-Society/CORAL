# 2025 Astrodynamics Assignment — Manned Lunar Landing

## 1. Background
In 1958, the Soviet Union and the United States began lunar exploration. In 1969, the United States achieved the first manned lunar landing, and by 1972, a total of 12 astronauts had landed on the Moon. After decades of silence, entering the 21st century, with the development of space technology and the rise of the "sustainable exploration" concept, returning to the Moon, developing lunar resources, and establishing long-term lunar bases have become inevitable trends and competitive hotspots in global space activities.

China has had the grand aspiration of "Chang'e flying to the Moon" since ancient times. In 2004, China's first lunar exploration project was officially approved and implemented. To date, the three-phase unmanned lunar exploration project has been successfully completed, and the lunar exploration project has officially entered the manned lunar landing phase. On October 30, 2025, at the Shenzhou 21 manned flight mission press conference, Zhang Jingbo, spokesperson for China's Manned Space Engineering and Director of the Comprehensive Planning Bureau of the China Manned Space Engineering Office, stated: "We are firmly committed to achieving the goal of Chinese landing on the Moon before 2030."

This astrodynamics assignment is based on the "Manned Lunar Landing" scenario. Design Earth-Moon transfer trajectories under the planar circular restricted three-body model to transport astronauts to lunar orbit to perform missions and return, while maximizing the lunar payload capacity.

## 2. Problem Description
To achieve routine manned lunar landing operations, humanity has established a **fuel resupply spacecraft** on a planar periodic orbit near the Earth-Moon L1 Lagrange point, utilizing restricted three-body dynamics properties of the Earth-Moon system. This spacecraft can provide fuel refueling or offloading services for manned spacecraft.

### 2.1 Main Mission Flow
1. **Departure**: Manned spacecraft carrying astronauts departs from initial Earth orbit to target lunar orbit.
2. **Lunar Landing & Mission**: Astronauts land on Moon, conduct scientific missions, deploy payload; manned spacecraft remains in target lunar orbit; after mission completion, astronauts return to manned spacecraft.
3. **Return**: Manned spacecraft carrying astronauts departs from target lunar orbit and returns to Earth.

### 2.2 Flow Details and Clarifications
* **A. Departure Maneuver**: Manned spacecraft can apply one impulsive maneuver Δv_dep from any phase of the initial orbit to depart. This maneuver is considered provided by the launch rocket (see "Mass Calculation" section); all subsequent maneuvers are impulsive maneuvers and are considered to use the spacecraft's own fuel.
* **B. Lunar Orbit Constraints**: Manned spacecraft can arrive at the target lunar orbit at any phase, but must satisfy the "circular orbit" requirement; after mission completion, it can depart from any phase of the target lunar orbit. The orbit plane direction (prograde/retrograde) for arrival and departure must be consistent.
* **C. Resupply Rendezvous (Optional)**: During the Earth-Moon or Moon-Earth transfer processes in steps (1) and (3), the manned spacecraft can be designed to rendezvous with the fuel resupply spacecraft for refueling or fuel offloading.
    * **Rendezvous Requirement**: Position and velocity vectors of manned spacecraft and resupply spacecraft must be equal.
    * **Rendezvous State**: After docking, refueling or offloading time is not counted. The orbital state of the manned spacecraft is considered the same as the resupply spacecraft until the manned spacecraft performs a separation maneuver.

## 3. Orbit Definitions
* **Initial Orbit**: Circular orbit at 400 km altitude relative to Earth (prograde or retrograde both allowed).
* **Target Orbit**: Circular orbit at 100 km altitude relative to Moon (prograde or retrograde both allowed).
* **Return Orbit**: Orbit with periapsis altitude of 0 km; spacecraft is considered returned to Earth at periapsis.
* **Resupply Orbit**: Planar Lyapunov periodic orbit near L1 libration point, a special three-body orbit (specific parameters in model section below).

> **Note**: The initial circular orbit around Earth and the target circular orbit around Moon are both two-body orbits relative to Earth or Moon in the "inertial frame". Must distinguish between "synodic frame (rotating frame)" and "inertial frame" velocity calculations.

## 4. Mass Calculation
The total mass of the manned spacecraft consists of three parts:
1. **Spacecraft dry mass (including astronauts)**: 10000 kg.
2. **Fuel**: Tank can store a maximum of 15000 kg fuel, can be partially filled.
3. **Lunar payload**: Remaining load after dry mass and fuel. All lunar payload is considered left on the Moon after lunar landing mission.

### 4.1 Initial Mass and Launch Energy
Due to launch rocket capability limitations, the spacecraft's initial mass M₀ (kg) relates to launch energy C₃ (km²/s²) as:

M₀ = 25000 - 1000·C₃

where launch energy C₃ is calculated as (twice the two-body orbital energy relative to Earth when departing from Earth's initial orbit):

C₃ = v_dep² - 2μ_e/r_dep

### 4.2 Fuel Consumption Calculation
Impulsive maneuvers applied during the mission will be converted to fuel consumption. Assuming the spacecraft applies a velocity increment Δv (m/s), the remaining mass M_f after the maneuver is:

M_f = M·exp(-Δv/3000)

where M is the spacecraft mass before the maneuver. **The fuel consumption for each maneuver must not exceed the remaining fuel amount.**

> **Example**:
> Assuming the spacecraft departs from Earth's initial orbit with C₃=0, the initial mass is 25000 kg. If only carrying 8000 kg fuel, after subtracting the dry mass of 10000 kg, the remaining 7000 kg is the lunar payload.
> Assuming the spacecraft has 4000 kg fuel remaining when arriving at the target lunar orbit, all lunar payload is left on the Moon. After the scientific mission is completed, the total mass of the manned spacecraft is the sum of dry mass and fuel mass, i.e., 14000 kg.

## 5. Planar Circular Restricted Three-Body Model

### 5.1 Parameter Constants
* Earth gravitational parameter: μ_e = 398600 km³/s²
* Moon gravitational parameter: μ_m = 4903 km³/s²
* Earth radius: R_e = 6378 km
* Moon radius: R_m = 1737 km
* Earth-Moon distance (normalization unit): [LU] = 384400 km

### 5.2 Dynamics Differential Equations
In the Earth-Moon "synodic frame", the equations are:

ẍ = 2ẏ + x - (1-μ)(x+μ)/r₁³ - μ(x-1+μ)/r₂³
ÿ = -2ẋ + y - (1-μ)y/r₁³ - μy/r₂³

where:
r₁ = √((x+μ)² + y²)
r₂ = √((x-1+μ)² + y²)

### 5.3 Resupply Spacecraft Orbit Calculation
* **Initial State**: At initial time t=0, resupply spacecraft position is r_supply(0) = [0.8, 0]ᵀ.
* **Solution Requirement**: Need to solve the resupply spacecraft velocity v_supply(0) at this moment and the orbit period T according to periodic orbit requirements.
* **State Propagation**: At some time t=t_i, the position and velocity vectors of the resupply spacecraft are calculated as follows (using modulo to avoid error amplification):

    t̂_i = mod(t_i, T)
    r_supply(t_i) = r_supply(t̂_i)
    v_supply(t_i) = v_supply(t̂_i)

## 6. Constraints

1. **Total Duration Limit**: From manned spacecraft departing initial orbit to returning to Earth, the entire process cannot exceed **100 days**.
2. **Lunar Surface Stay Time**: Astronauts' lunar scientific mission duration is **3.0 ~ 10.0 days** (i.e., the time interval between arriving at and departing from the target lunar orbit).
3. **Spatial Range Limit**: All transfer trajectories must be limited within a radius of **2 Earth-Moon distances** (considering telemetry communication limitations).
4. **Altitude and Safety Limits**:
    * Orbit altitude relative to Moon cannot be lower than 100 km.
    * Before entering return orbit, orbit altitude relative to Earth cannot be lower than 400 km.
    * **Remaining fuel when returning to Earth cannot exceed 100 kg**.
5. **Patch Point Precision Error**: Position and velocity allowable errors at departure, rendezvous, arrival and other patch points of the manned spacecraft:

    ||r_manned(t) - r_target(t)|| ≤ 10⁻⁶ [LU]
    ||v_manned(t) - v_target(t)|| ≤ 10⁻⁶ [VU]

    where [LU] is Earth-Moon distance, [VU] is the corresponding velocity dimension.

## 7. Results File Format (results.txt)

To verify the correctness of calculation results, a results file must be submitted with the name and extension uniformly as `results.txt`.

### 7.1 Data Format Description
Except for the first column (Event) which is an integer, all other data uses **scientific notation** with **12 significant digits**.

| Column | Title | Unit | Data Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Event | - | int | Event node code (see 7.2) |
| 2 | Time | TU | float | Normalized time (initial is 0) |
| 3 | X | LU | float | Synodic frame X position component |
| 4 | Y | LU | float | Synodic frame Y position component |
| 5 | Vx | VU | float | Synodic frame X velocity component |
| 6 | Vy | VU | float | Synodic frame Y velocity component |
| 7 | ΔVx | VU | float | Velocity increment X component |
| 8 | ΔVy | VU | float | Velocity increment Y component |
| 9 | Mfuel | kg | float | Remaining fuel mass |
| 10 | Mcarry | kg | float | Lunar payload mass |

### 7.2 Event Code Definitions
* `-1`: Spacecraft applies maneuver
* `0`: Non-maneuvering orbit propagation segment
* `1`: Departure from Earth's initial orbit
* `2`: Arrival at target lunar orbit (simultaneously considered as conducting lunar scientific mission)
* `3`: Departure from target lunar orbit (simultaneously considered as scientific mission completion)
* `4`: Return to Earth
* `5`: Rendezvous with resupply spacecraft

### 7.3 Recording Rules Supplement
1. **Non-maneuvering propagation segment (Event 0)**: Requires at least two rows of data (first row initial state, second row final state).
2. **Apply maneuver (Event -1)**: Requires at least two rows of data.
    * First row: State **before** maneuver, impulse components are 0.
    * Second row: State **after** maneuver, impulse components are design values, and must calculate remaining fuel mass.
3. **Mission/Stay (Event 2 & 3)**: Event 2 and Event 3 should be two consecutive rows, cannot insert other events in between.
4. **Resupply (Event 5)**: If performing fuel refueling or offloading, need two rows of data (first row state before refueling/offloading; second row state after refueling/offloading).
5. **End (Event 4)**: The file's **last row must be Event 4**. If missing, considered incomplete; if appearing early, considered mission ended prematurely.