# OSPF Configuration Guide - Cisco IOS/IOS-XE

## Overview

OSPF (Open Shortest Path First) is a link-state routing protocol defined in RFC 2328 (OSPFv2) and RFC 5340 (OSPFv3). It uses the Dijkstra SPF algorithm to compute the shortest path tree and supports VLSM, CIDR, and hierarchical design through areas.

## Basic OSPF Configuration

### Enable OSPF Process

```
router ospf 1
 router-id 1.1.1.1
 network 10.0.0.0 0.0.0.255 area 0
 network 192.168.1.0 0.0.0.255 area 1
```

The `router-id` should always be explicitly configured. If not set, the router selects the highest loopback IP or the highest interface IP.

### Interface-Level Configuration (Recommended)

```
interface GigabitEthernet0/0
 ip ospf 1 area 0
 ip ospf cost 10
 ip ospf priority 100
```

Interface-level configuration is preferred over `network` statements for clarity and precision.

## OSPF Authentication

### Plain Text Authentication (NOT Recommended)

```
interface GigabitEthernet0/0
 ip ospf authentication
 ip ospf authentication-key MYPASSWORD
```

### MD5 Authentication (Recommended)

```
interface GigabitEthernet0/0
 ip ospf authentication message-digest
 ip ospf message-digest-key 1 md5 SECURE_KEY_HERE
```

### Area-Level Authentication

```
router ospf 1
 area 0 authentication message-digest
```

When area-level authentication is configured, all interfaces in that area must use MD5 authentication.

## OSPF Network Types

| Network Type | Hello/Dead | DR/BDR | Default On |
|---|---|---|---|
| Broadcast | 10/40 | Yes | Ethernet |
| Point-to-Point | 10/40 | No | Serial (HDLC/PPP) |
| Non-Broadcast | 30/120 | Yes | Frame Relay |
| Point-to-Multipoint | 30/120 | No | Manual |

### Changing Network Type

```
interface GigabitEthernet0/0
 ip ospf network point-to-point
```

Use `point-to-point` on links between only two routers (even Ethernet) to avoid DR/BDR election overhead.

## OSPF Areas and Design

### Stub Area

Blocks external LSAs (Type 5). Injects a default route.

```
router ospf 1
 area 1 stub
```

All routers in the area must agree on stub configuration.

### Totally Stubby Area

Blocks both external and inter-area LSAs (Type 3 and 5).

```
! On ABR only:
router ospf 1
 area 1 stub no-summary

! On other routers in area:
router ospf 1
 area 1 stub
```

### NSSA (Not-So-Stubby Area)

Allows external routes via Type 7 LSA, converted to Type 5 at ABR.

```
router ospf 1
 area 2 nssa
```

## OSPF Timers and Tuning

### Hello and Dead Intervals

```
interface GigabitEthernet0/0
 ip ospf hello-interval 5
 ip ospf dead-interval 20
```

Timers must match on both sides of a link, or adjacency will not form.

### SPF Throttle

```
router ospf 1
 timers throttle spf 50 200 5000
```

Parameters: initial-delay (ms), second-delay (ms), max-wait (ms).

### LSA Throttle

```
router ospf 1
 timers throttle lsa all 100 200 5000
```

## OSPF Troubleshooting Commands

```
show ip ospf neighbor
show ip ospf interface brief
show ip ospf database
show ip route ospf
debug ip ospf adj
debug ip ospf events
```

### Common Issues

1. **Neighbor stuck in INIT**: Mismatched hello/dead timers, MTU mismatch, or ACL blocking OSPF
2. **Neighbor stuck in EXSTART/EXCHANGE**: MTU mismatch (use `ip ospf mtu-ignore` as workaround)
3. **Neighbor stuck in 2-WAY**: Expected on broadcast networks for non-DR/BDR routers
4. **Routes not appearing**: Check area configuration, stub flags, route filtering

### MTU Mismatch Fix

```
interface GigabitEthernet0/0
 ip ospf mtu-ignore
```

Note: This is a workaround. The proper fix is to match MTU on both sides.

## OSPFv3 (IPv6)

```
ipv6 unicast-routing

interface GigabitEthernet0/0
 ipv6 ospf 1 area 0

ipv6 router ospf 1
 router-id 1.1.1.1
```

OSPFv3 uses link-local addresses for neighbor relationships and requires explicit router-id configuration.

## OSPF Route Summarization

### Inter-Area Summarization (ABR)

```
router ospf 1
 area 1 range 10.1.0.0 255.255.0.0
```

### External Route Summarization (ASBR)

```
router ospf 1
 summary-address 172.16.0.0 255.255.0.0
```

## OSPF Passive Interface

```
router ospf 1
 passive-interface default
 no passive-interface GigabitEthernet0/0
```

Use `passive-interface default` and selectively enable OSPF on needed interfaces for security.

## OSPF Virtual Link

Used to connect a disconnected area to area 0 through a transit area.

```
! On both ABRs:
router ospf 1
 area 1 virtual-link 2.2.2.2
```

Where `2.2.2.2` is the router-id of the remote ABR.

## Best Practices

1. Always set explicit `router-id`
2. Use MD5 authentication on all OSPF interfaces
3. Use `passive-interface default` and selectively enable
4. Design with proper area hierarchy (area 0 as backbone)
5. Summarize routes at ABR boundaries
6. Use `point-to-point` network type on point-to-point links
7. Set reference bandwidth to match your fastest links: `auto-cost reference-bandwidth 100000`
