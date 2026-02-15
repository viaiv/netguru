# OSPF Configuration Guide - Juniper JunOS

## Overview

OSPF on Juniper JunOS follows the same RFC 2328/5340 standards as other vendors. Configuration uses Juniper's hierarchical CLI or `set` commands under `protocols ospf`.

## Basic OSPF Configuration

### Hierarchical Format

```
protocols {
    ospf {
        area 0.0.0.0 {
            interface ge-0/0/0.0;
            interface lo0.0 {
                passive;
            }
        }
    }
}
```

### Set Command Format

```
set protocols ospf area 0.0.0.0 interface ge-0/0/0.0
set protocols ospf area 0.0.0.0 interface lo0.0 passive
set routing-options router-id 1.1.1.1
```

The `router-id` is configured under `routing-options`, not inside the OSPF stanza.

## OSPF Authentication

### MD5 Authentication (Recommended)

```
set protocols ospf area 0.0.0.0 interface ge-0/0/0.0 authentication md5 1 key SECURE_KEY
```

### Simple Password (NOT Recommended)

```
set protocols ospf area 0.0.0.0 interface ge-0/0/0.0 authentication simple-password MYPASS
```

## OSPF Network Types

Juniper uses `interface-type` to set the OSPF network type:

```
set protocols ospf area 0.0.0.0 interface ge-0/0/0.0 interface-type p2p
```

Available types: `broadcast`, `p2p` (point-to-point), `nbma`, `p2mp` (point-to-multipoint).

## OSPF Areas

### Stub Area

```
set protocols ospf area 0.0.0.1 stub
```

### Totally Stubby Area

```
set protocols ospf area 0.0.0.1 stub no-summaries
```

### NSSA

```
set protocols ospf area 0.0.0.2 nssa
```

## OSPF Timers

```
set protocols ospf area 0.0.0.0 interface ge-0/0/0.0 hello-interval 5
set protocols ospf area 0.0.0.0 interface ge-0/0/0.0 dead-interval 20
set protocols ospf spf-options delay 200
set protocols ospf spf-options holddown 2000
set protocols ospf spf-options rapid-runs 3
```

## OSPF Route Summarization

### Inter-Area (ABR)

```
set protocols ospf area 0.0.0.1 area-range 10.1.0.0/16
```

### External (ASBR)

Use export policies to aggregate routes into OSPF.

## OSPF Troubleshooting Commands

```
show ospf neighbor
show ospf interface
show ospf database
show route protocol ospf
show ospf statistics
```

### Common Issues

1. **Neighbor stuck in Init**: Mismatched hello/dead timers, MTU mismatch, authentication mismatch
2. **Neighbor stuck in ExStart**: MTU mismatch (fix with matching MTU or BFD)
3. **Routes not in routing table**: Check export/import policies, area type
4. **Adjacency flapping**: Check physical layer, BFD timers

## OSPFv3 (IPv6)

```
set protocols ospf3 area 0.0.0.0 interface ge-0/0/0.0
set routing-options router-id 1.1.1.1
```

## Best Practices

1. Always configure explicit `router-id` under `routing-options`
2. Use MD5 authentication on all OSPF interfaces
3. Use passive on loopback and management interfaces
4. Use `p2p` interface-type on point-to-point links
5. Summarize routes at area boundaries with `area-range`
6. Set reference-bandwidth to match fastest link speed
7. Use BFD for fast failure detection: `set protocols ospf area 0 interface ge-0/0/0.0 bfd-liveness-detection minimum-interval 300`
