N-Body Simulation Problem - 100,000 Particles
=============================================

Problem Setting
---------------
Design and optimize a high-performance parallel N-body simulation. In physics and astronomy, an N-body simulation models the dynamics of particles under gravitational forces. The available hardware is an AWS c7i.4xlarge.

The challenge involves optimizing:
- **Loop parallelization**: Efficient parallel force computation across particles
- **Acceleration structures**: Use structures such as quad-tree for O(N log N) instead of O(N²), or other structures.
- **Load balancing**: Handling varying workloads per particle
- **Parallel Programming Libraries**: Proper use of libraries like OpenMP

This variant tests performance on **100,000 particles** with 3 simulation iterations.

Target
------
- **Primary**: Ensure numerical correctness (tolerance: 1e-2)
- **Secondary**: Maximize speedup over parallel brute-force baseline (higher is better)
- **Tertiary**: Use algorithmic improvements (quad-tree, spatial hashing) to beat O(N²)

Solution Format
---------------
Submit a single C++ file (`.cpp`) that implements a `Simulator` class:

```cpp
#include "world.h"
#include <omp.h>

class MySimulator : public Simulator {
private:
    // Persistent state across simulation steps
    int numThreads = 8;
    // Could store acceleration structures, pre-allocated buffers, etc.

public:
    void init(int numParticles, StepParameters params) override {
        // Called once before simulation starts
        // Set thread count, pre-allocate structures, etc.
        omp_set_num_threads(numThreads);
    }

    void simulateStep(std::vector<Particle> &particles,
                      std::vector<Particle> &newParticles,
                      StepParameters params) override {
        // Called each simulation step
        // For each particle i:
        //   1. Compute total force from particles within params.cullRadius
        //   2. Update particle using updateParticle()
        //   3. Store result in newParticles[i]
    }
};

// Factory function - must be implemented
Simulator* createSimulator() {
    return new MySimulator();
}
```

Provided Types and Functions (in world.h)
-----------------------------------------
```cpp
struct Vec2 {
    float x, y;
    // Operators: +, -, *, length(), length2()
};

struct Particle {
    int id;
    float mass;
    Vec2 position;
    Vec2 velocity;
};

struct StepParameters {
    float deltaTime = 0.2f;
    float cullRadius = 1.0f;  // Only consider particles within this distance
};

// Simulator base class
class Simulator {
public:
    virtual ~Simulator() = default;
    virtual void init(int numParticles, StepParameters params) {}  // Optional
    virtual void simulateStep(std::vector<Particle> &particles,
                              std::vector<Particle> &newParticles,
                              StepParameters params) = 0;  // Required
};

// Compute gravitational force between two particles
// Returns Vec2(0,0) if distance > cullRadius or distance < 1e-3
inline Vec2 computeForce(const Particle &target, const Particle &attractor,
                         float cullRadius) {
  auto dir = (attractor.position - target.position);
  auto dist = dir.length();
  if (dist < 1e-3f)
    return Vec2(0.0f, 0.0f);
  dir *= (1.0f / dist);
  if (dist > cullRadius)
    return Vec2(0.0f, 0.0f);
  if (dist < 1e-1f)
    dist = 1e-1f;
  const float G = 0.01f;
  Vec2 force = dir * target.mass * attractor.mass * (G / (dist * dist));
  if (dist > cullRadius * 0.75f) {
    float decay = 1.0f - (dist - cullRadius * 0.75f) / (cullRadius * 0.25f);
    force *= decay;
  }
  return force;
}

// Apply force to particle and integrate position/velocity
inline Particle updateParticle(const Particle &pi, Vec2 force,
                               float deltaTime) {
  Particle result = pi;
  result.velocity += force * (deltaTime / pi.mass);
  result.position += result.velocity * deltaTime;
  return result;
}
```

Baseline
--------
The baseline is a simple OpenMP parallel brute-force O(N²) implementation:

```cpp
// Baseline for N-body simulation - simple OpenMP parallel brute-force
// O(N²) approach with parallel outer loop
// Solutions should aim to beat this baseline

#include "world.h"
#include <omp.h>

class BaselineSimulator : public Simulator {
private:
    int numThreads = 8;
    
public:
    void init(int numParticles, StepParameters params) override {
        omp_set_num_threads(numThreads);
    }
    
    void simulateStep(std::vector<Particle> &particles,
                      std::vector<Particle> &newParticles,
                      StepParameters params) override {
        #pragma omp parallel for schedule(dynamic, 16)
        for (int i = 0; i < (int)particles.size(); i++) {
            auto pi = particles[i];
            Vec2 force = Vec2(0.0f, 0.0f);
            
            for (size_t j = 0; j < particles.size(); j++) {
                if (j == (size_t)i) continue;
                if ((pi.position - particles[j].position).length() < params.cullRadius) {
                    force += computeForce(pi, particles[j], params.cullRadius);
                }
            }
            
            newParticles[i] = updateParticle(pi, force, params.deltaTime);
        }
    }
};

Simulator* createSimulator() {
    return new BaselineSimulator();
}
```

To beat the baseline, use algorithmic improvements like acceleration structures.

Please generate a `.cpp` file that follows the solution's interface above, with the exact same
signatures. The `Simulator` you write will be used in the following way: 

```cpp
double runSimulation(World& world, Simulator* sim, 
                     StepParameters params, int numIterations) {
  Timer timer;
  timer.reset();
  
  // Initialize simulator at the start of each run (clean state)
  sim->init(world.particles.size(), params);
  
  for (int iter = 0; iter < numIterations; iter++) {
    world.newParticles.resize(world.particles.size());
    sim->simulateStep(world.particles, world.newParticles, params);
    world.particles.swap(world.newParticles);
  }
  
  return timer.elapsed();
}
```

Compilation
-----------
Your code is compiled with:
```bash
g++ -O2 -fopenmp -std=c++17 -I. -o benchmark solution.cpp
```

Requirements:
- Can use OpenMP for parallelization
- Must implement a `Simulator` subclass and `createSimulator()` factory function
- May define additional helper classes/functions as needed
- Do NOT modify `computeForce` or `updateParticle` functions

Correctness
-----------

We will use the `BaselineSimulator` to get a reference particles positions and compare the solution you generated with the following code. We use a tolerance of `1e-2f`. If you fail the correctness check, you will get a score of zero.

```cpp
bool checkForCorrectness(const World& refW, const World& w, float tolerance = 1e-2f) {
  if (w.particles.size() != refW.particles.size()) {
    std::cerr << "Mismatch: number of particles " << w.particles.size()
              << " does not match reference " << refW.particles.size() << std::endl;
    return false;
  }

  for (size_t i = 0; i < w.particles.size(); i++) {
    auto errorX = std::abs(w.particles[i].position.x - refW.particles[i].position.x);
    auto errorY = std::abs(w.particles[i].position.y - refW.particles[i].position.y);
    if (errorX > tolerance || errorY > tolerance) {
      std::cerr << "Mismatch at index " << i
                << ": result (" << w.particles[i].position.x << ", "
                << w.particles[i].position.y << ")"
                << " should be (" << refW.particles[i].position.x << ", "
                << refW.particles[i].position.y << ")" << std::endl;
      return false;
    }
  }
  return true;
}
```

Scoring (0-100)
---------------
Performance is measured by speedup over the parallel brute-force baseline:

```
speedup = baseline_time / solution_time
raw_score = min(speedup, 10.0)  # Cap at 10x speedup
score = (raw_score - 1.0) / 9.0 * 100  # Map 1x-10x to 0-100
```

- 0 points = No speedup (1x baseline performance)
- ~11 points = 2x speedup
- ~33 points = 4x speedup
- ~56 points = 6x speedup
- 100 points = 10x+ speedup

Note: With 100k particles, algorithmic improvements can yield massive speedups.
The brute-force baseline is extremely slow, so good solutions should achieve high speedups.

Evaluation Details
------------------
- Tested with 100,000 particles
- 3 simulation iterations
- Space size: 100.0, cullRadius: 25.0
- Performance measured as median of 3 runs
- Correctness verified with tolerance: position error < 1e-2
- Fixed random seed for reproducibility
