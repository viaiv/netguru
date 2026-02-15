# BGP Configuration Guide - Juniper JunOS

## Overview

BGP on Juniper JunOS is configured under `protocols bgp`. Juniper uses a group-based model where neighbors are organized into groups with shared attributes.

## Basic BGP Configuration

### eBGP

```
set routing-options autonomous-system 65001
set routing-options router-id 1.1.1.1

set protocols bgp group EBGP-PEERS type external
set protocols bgp group EBGP-PEERS neighbor 10.0.0.2 peer-as 65002
set protocols bgp group EBGP-PEERS neighbor 10.0.0.2 description "Link to ISP"
```

### iBGP

```
set protocols bgp group IBGP-PEERS type internal
set protocols bgp group IBGP-PEERS local-address 1.1.1.1
set protocols bgp group IBGP-PEERS neighbor 2.2.2.2
set protocols bgp group IBGP-PEERS neighbor 3.3.3.3
```

## BGP Authentication

```
set protocols bgp group EBGP-PEERS authentication-key SECURE_KEY
```

Or per-neighbor:

```
set protocols bgp group EBGP-PEERS neighbor 10.0.0.2 authentication-key PEER_KEY
```

## BGP Route Policies

Juniper BGP requires explicit policies to advertise routes (unlike Cisco).

### Export Policy (Advertise Routes)

```
set policy-options policy-statement EXPORT-CONNECTED term 1 from protocol direct
set policy-options policy-statement EXPORT-CONNECTED term 1 then accept

set protocols bgp group EBGP-PEERS export EXPORT-CONNECTED
```

### Import Policy (Filter Received Routes)

```
set policy-options prefix-list ALLOWED-PREFIXES 10.0.0.0/8
set policy-options policy-statement IMPORT-FILTER term ALLOW from prefix-list ALLOWED-PREFIXES
set policy-options policy-statement IMPORT-FILTER term ALLOW then accept
set policy-options policy-statement IMPORT-FILTER term DENY then reject

set protocols bgp group EBGP-PEERS import IMPORT-FILTER
```

## BGP Route Reflection

```
set protocols bgp group IBGP-CLIENTS type internal
set protocols bgp group IBGP-CLIENTS cluster 1.1.1.1
set protocols bgp group IBGP-CLIENTS neighbor 4.4.4.4
```

## BGP Multipath

```
set routing-options forwarding-table export ECMP-POLICY
set policy-options policy-statement ECMP-POLICY term 1 then load-balance per-packet
set protocols bgp group EBGP-PEERS multipath multiple-as
```

## BGP Graceful Restart

```
set protocols bgp group EBGP-PEERS graceful-restart
```

## BGP BFD

```
set protocols bgp group EBGP-PEERS bfd-liveness-detection minimum-interval 300
set protocols bgp group EBGP-PEERS bfd-liveness-detection multiplier 3
```

## BGP Troubleshooting Commands

```
show bgp summary
show bgp neighbor <IP>
show route protocol bgp
show route advertising-protocol bgp <neighbor>
show route receive-protocol bgp <neighbor>
show bgp group
```

### Common Issues

1. **Session not established**: Check TCP port 179 reachability, authentication, AS number
2. **No routes received**: Check import policy (Juniper rejects by default without policy)
3. **No routes advertised**: Check export policy, routes must be explicitly exported
4. **Flapping sessions**: Check hold-time, MTU, BFD timers, physical link stability

## Best Practices

1. Always use authentication on BGP sessions
2. Use routing policies for both import and export
3. Configure explicit `router-id` and `autonomous-system`
4. Use loopback addresses for iBGP sessions
5. Enable BFD for fast failure detection
6. Use prefix-limits to protect against route leaks: `set protocols bgp group EBGP-PEERS neighbor 10.0.0.2 family inet unicast prefix-limit maximum 10000`
7. Enable graceful restart for non-stop routing
