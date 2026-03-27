// interactor.cpp
// Interactive process using testlib: hides circle center and radius, returns segment-circle intersection length
// Compile with testlib: g++ interactor.cpp -o interactor -O2

#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char *argv[]) {
    registerInteraction(argc, argv);

    // Read hidden circle center and radius from inf (input data)
    // Input format: three lines: cx cy r
    // Constraints: 0 <= cx,cy <= 1e5, 100 <= r <= ...
    int cx, cy, r;
    cx = inf.readInt();
    cy = inf.readInt();
    r  = inf.readInt();

    const int MAX_COORD = 100000;
    const int MAX_QUERIES = 1024;
    int queries = 0;

    // helper lambda: compute length of intersection between segment AB and circle(center C, radius r)
    auto segment_circle_intersection_length = [&](double ax, double ay, double bx, double by) -> double {
        double cx_d = (double)cx;
        double cy_d = (double)cy;
        double r_d  = (double)r;

        double dx = bx - ax;
        double dy = by - ay;
        double L = sqrt(dx*dx + dy*dy);
        if (L == 0.0) return 0.0;

        // Parameterize P(t) = A + t*(d), t in [0,1]
        // Solve |P(t)-C|^2 = r^2 -> at^2 + bt + c = 0
        double fx = ax - cx_d;
        double fy = ay - cy_d;
        double a = dx*dx + dy*dy;
        double b = 2.0*(fx*dx + fy*dy);
        double c = fx*fx + fy*fy - r_d*r_d;

        double eps = 1e-12;
        double disc = b*b - 4.0*a*c;
        if (disc < -1e-10) {
            // no real roots: either whole segment inside or outside
            double da = sqrt(fx*fx + fy*fy);
            double db = sqrt((bx-cx_d)*(bx-cx_d) + (by-cy_d)*(by-cy_d));
            if (da <= r_d + 1e-12 && db <= r_d + 1e-12) {
                return L;
            } else {
                return 0.0;
            }
        }
        if (disc < 0.0) disc = 0.0;
        double sd = sqrt(disc);
        double t1 = (-b - sd) / (2.0 * a);
        double t2 = (-b + sd) / (2.0 * a);
        double lo = min(t1, t2);
        double hi = max(t1, t2);
        double seg_lo = max(0.0, lo);
        double seg_hi = min(1.0, hi);
        if (seg_hi <= seg_lo + 1e-15) return 0.0;
        double len = (seg_hi - seg_lo) * L;
        if (len < 0.0) len = 0.0;
        return len;
    };

    // main loop: read tokens from contestant (ouf)
    while (true) {
        // read next word (command)
        string cmd;
        try {
            cmd = ouf.readWord();
        } catch (...) {
            // unexpected EOF from contestant
            quitf(_pe, "Unexpected EOF from contestant");
        }

        if (cmd == "query") {
            // read four integers
            long long x1_ll = ouf.readLong();
            long long y1_ll = ouf.readLong();
            long long x2_ll = ouf.readLong();
            long long y2_ll = ouf.readLong();

            // validate coordinates are integers in [0, MAX_COORD]
            if (x1_ll < 0 || x1_ll > MAX_COORD ||
                y1_ll < 0 || y1_ll > MAX_COORD ||
                x2_ll < 0 || x2_ll > MAX_COORD ||
                y2_ll < 0 || y2_ll > MAX_COORD) {
                quitf(_wa, "Coordinates out of range: (%lld,%lld)-(%lld,%lld)", x1_ll, y1_ll, x2_ll, y2_ll);
            }

            // distinct points required
            if (x1_ll == x2_ll && y1_ll == y2_ll) {
                quitf(_wa, "Query endpoints must be distinct");
            }

            queries++;
            if (queries > MAX_QUERIES) {
                quitf(_wa, "Too many queries: %d (limit %d)", queries, MAX_QUERIES);
            }

            double x1 = (double)x1_ll;
            double y1 = (double)y1_ll;
            double x2 = (double)x2_ll;
            double y2 = (double)y2_ll;

            double ans_len = segment_circle_intersection_length(x1, y1, x2, y2);

            // output with 7 decimal places
            // Use printf and flush so contestant receives immediately
            printf("%.7f\n", ans_len);
            fflush(stdout);

        } else if (cmd == "answer") {
            // contestant submits final answer: three integers
            long long ax = ouf.readLong();
            long long ay = ouf.readLong();
            long long ar = ouf.readLong();

            // Validate ranges (basic)
            if (ax < 0 || ax > MAX_COORD || ay < 0 || ay > MAX_COORD || ar < 0 || ar > MAX_COORD) {
                quitf(_wa, "Answer values out of range");
            }

            // Check exact match with hidden integers
            if ((int)ax == cx && (int)ay == cy && (int)ar == r) {
			    double scoreRatio = 1.0 - (double)queries / (double)MAX_QUERIES;
			    if (scoreRatio < 0.0) scoreRatio = 0.0;
			
			    // Score calculation example: fewer queries are better
			    // Alternative: non-linear scoring, e.g., score = (1 - queries/1024)^2

			    quitp(scoreRatio, "Ratio: %lf", scoreRatio);
            } else {
                quitf(_wa, "Wrong answer. Expected (%d,%d,%d) but got (%lld,%lld,%lld)", cx, cy, r, ax, ay, ar);
            }
            // we'll never reach here
        } else {
            // invalid command
            quitf(_pe, "Unknown command: %s", cmd.c_str());
        }
    }

    return 0;
}
