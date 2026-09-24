# Data layout: array-of-structs to struct-of-arrays

When: a loop updates or reads only a subset of a struct's fields inside
a large array of structs (has_struct_array feature), so most of each
cache line loaded is wasted bandwidth on unused fields.

How: replace a struct-of-doubles array (x, y, z, vx, vy, vz per element)
with separate parallel arrays, one per field. Update all access sites
consistently; this is a mechanical but invasive rewrite.

Pitfalls: if most call sites actually touch all fields together (true
AoS-friendly access), converting to SoA can hurt locality instead of
helping; only apply when the profile shows a field-selective access
pattern, e.g. a loop that advances position using velocity while never
touching mass or charge in the same pass.

Expected gain: 1.3-2.5x when the untouched-field fraction is large
(struct much bigger than the fields actually used in the loop).
