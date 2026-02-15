# BGP Configuration Guide - Arista EOS

## Overview

BGP on Arista EOS follows Cisco IOS CLI syntax closely. Arista supports advanced features like EVPN, multi-agent routing, and extensive BGP community support.

## Basic BGP Configuration

### eBGP

```
router bgp 65001
   router-id 1.1.1.1
   neighbor 10.0.0.2 remote-as 65002
   neighbor 10.0.0.2 description ISP-Upstream
   network 192.168.0.0/24
```

### iBGP

```
router bgp 65001
   router-id 1.1.1.1
   neighbor 2.2.2.2 remote-as 65001
   neighbor 2.2.2.2 update-source Loopback0
   neighbor 2.2.2.2 send-community
```

## BGP Authentication

```
router bgp 65001
   neighbor 10.0.0.2 password SECURE_KEY
```

## BGP Address Families

Arista supports multiple address families:

```
router bgp 65001
   address-family ipv4 unicast
      neighbor 10.0.0.2 activate
      network 192.168.0.0/24
   !
   address-family ipv6 unicast
      neighbor 2001:db8::2 activate
```

## BGP with EVPN

```
router bgp 65001
   address-family evpn
      neighbor SPINE-PEERS activate
   !
   vlan 100
      rd auto
      route-target both 100:100
      redistribute learned
```

## BGP Route Maps and Prefix Lists

```
ip prefix-list ALLOWED-ROUTES seq 10 permit 10.0.0.0/8 le 24
ip prefix-list ALLOWED-ROUTES seq 20 permit 172.16.0.0/12 le 24

route-map IMPORT-FILTER permit 10
   match ip address prefix-list ALLOWED-ROUTES

router bgp 65001
   neighbor 10.0.0.2 route-map IMPORT-FILTER in
```

## BGP Route Reflection

```
router bgp 65001
   neighbor 4.4.4.4 remote-as 65001
   neighbor 4.4.4.4 route-reflector-client
   bgp cluster-id 1.1.1.1
```

## BGP Multipath

```
router bgp 65001
   maximum-paths 4
   maximum-paths 4 ecmp 16
```

## BGP Graceful Restart

```
router bgp 65001
   graceful-restart restart-time 300
   graceful-restart
```

## BGP BFD

```
router bgp 65001
   neighbor 10.0.0.2 bfd
```

## BGP with VRF

```
router bgp 65001
   vrf CUSTOMER-A
      rd 65001:100
      route-target export 65001:100
      route-target import 65001:100
      neighbor 10.1.0.2 remote-as 65100
      neighbor 10.1.0.2 activate
```

## BGP Troubleshooting Commands

```
show ip bgp summary
show ip bgp neighbor <IP>
show ip bgp
show ip bgp community
show ip route bgp
show bgp evpn summary
```

### Common Issues

1. **Session not established**: Check TCP 179 reachability, authentication, AS number, update-source
2. **No routes received**: Check route-maps, prefix-lists, address-family activation
3. **No routes advertised**: Routes must be in RIB and matched by `network` or `redistribute`
4. **EVPN routes not working**: Check VXLAN config, route-targets, address-family evpn activation
5. **Session flapping**: Check hold-time, MTU, BFD, physical link

## Multi-Agent Routing

Arista supports `service routing protocols model multi-agent` for improved convergence:

```
service routing protocols model multi-agent
```

This separates BGP, OSPF, and other protocols into individual processes for better stability.

## Best Practices

1. Always use authentication on BGP sessions
2. Use prefix-limits to protect against route leaks: `neighbor 10.0.0.2 maximum-routes 10000`
3. Configure explicit `router-id`
4. Use loopback for iBGP sessions with `update-source`
5. Enable BFD for fast failure detection
6. Use `service routing protocols model multi-agent` for production
7. Apply route-maps on all eBGP sessions (both in and out)
8. Use graceful restart for non-stop forwarding
