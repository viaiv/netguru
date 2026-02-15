# OSPF Configuration Guide - Arista EOS

## Overview

OSPF on Arista EOS follows the same CLI syntax as Cisco IOS. Arista EOS is based on a Linux kernel with a Cisco-compatible CLI, making configuration familiar to Cisco engineers.

## Basic OSPF Configuration

```
router ospf 1
   router-id 1.1.1.1
   network 10.0.0.0/24 area 0.0.0.0
   network 192.168.1.0/24 area 0.0.0.1
```

### Interface-Level Configuration (Recommended)

```
interface Ethernet1
   ip ospf area 0.0.0.0
   ip ospf cost 10
   ip ospf priority 100
```

Note: Arista uses `Ethernet` interface naming (not GigabitEthernet).

## OSPF Authentication

### MD5 Authentication (Recommended)

```
interface Ethernet1
   ip ospf authentication message-digest
   ip ospf message-digest-key 1 md5 SECURE_KEY
```

### Area-Level Authentication

```
router ospf 1
   area 0.0.0.0 authentication message-digest
```

## OSPF Network Types

```
interface Ethernet1
   ip ospf network point-to-point
```

Available types: `broadcast`, `point-to-point`, `non-broadcast`, `point-to-multipoint`.

## OSPF Areas

### Stub Area

```
router ospf 1
   area 0.0.0.1 stub
```

### Totally Stubby Area

```
router ospf 1
   area 0.0.0.1 stub no-summary
```

### NSSA

```
router ospf 1
   area 0.0.0.2 nssa
```

## OSPF Timers

```
interface Ethernet1
   ip ospf hello-interval 5
   ip ospf dead-interval 20

router ospf 1
   timers throttle spf 50 200 5000
   timers throttle lsa all 100 200 5000
```

## OSPF with VRF

```
router ospf 1 vrf MGMT
   router-id 10.0.0.1
   network 10.0.0.0/24 area 0.0.0.0
```

## OSPF Route Summarization

### Inter-Area (ABR)

```
router ospf 1
   area 0.0.0.1 range 10.1.0.0/16
```

### External (ASBR)

```
router ospf 1
   summary-address 172.16.0.0/16
```

## OSPF Troubleshooting Commands

```
show ip ospf neighbor
show ip ospf interface brief
show ip ospf database
show ip route ospf
show ip ospf
```

### Common Issues

1. **Neighbor stuck in Init**: Mismatched timers, MTU mismatch, ACL blocking multicast 224.0.0.5/6
2. **Neighbor stuck in ExStart**: MTU mismatch (fix with `ip ospf mtu-ignore`)
3. **Routes missing**: Check area config, passive interfaces, route-maps
4. **High CPU from OSPF**: Check SPF throttle timers, unstable links causing frequent recalculations

## OSPF Passive Interface

```
router ospf 1
   passive-interface default
   no passive-interface Ethernet1
```

## Best Practices

1. Always set explicit `router-id`
2. Use MD5 authentication on all OSPF interfaces
3. Use `passive-interface default` and selectively enable on transit interfaces
4. Use `point-to-point` on point-to-point links
5. Configure `auto-cost reference-bandwidth 100000` for 100G environments
6. Use BFD for sub-second failure detection: `ip ospf bfd`
7. Summarize routes at ABR boundaries
