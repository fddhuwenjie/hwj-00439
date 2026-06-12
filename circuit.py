#!/usr/bin/env python3
import json
import sys
import argparse
from collections import defaultdict, deque
from typing import List, Dict, Tuple, Optional, Any, Union, Set
import copy
import itertools

SignalValue = Union[int, List[int]]


class Signal:
    def __init__(self, value: SignalValue = 0, width: int = 1):
        if isinstance(value, list):
            self.width = len(value)
            self.bits = [int(b) & 1 for b in value]
        else:
            self.width = width
            if width == 1:
                self.bits = [int(value) & 1]
            else:
                self.bits = [(int(value) >> i) & 1 for i in range(width)]

    def __getitem__(self, idx: int) -> int:
        if isinstance(idx, slice):
            bits = self.bits[idx]
            return Signal(bits)
        return self.bits[idx]

    def __setitem__(self, idx: int, value: int):
        self.bits[idx] = int(value) & 1

    def to_int(self) -> int:
        result = 0
        for i, b in enumerate(self.bits):
            result |= (b << i)
        return result

    def __eq__(self, other) -> bool:
        if isinstance(other, Signal):
            return self.bits == other.bits
        return False

    def __repr__(self) -> str:
        if self.width == 1:
            return str(self.bits[0])
        bits_str = ''.join(str(b) for b in reversed(self.bits))
        return f"{bits_str}({self.to_int()})"

    def copy(self) -> 'Signal':
        s = Signal(width=self.width)
        s.bits = self.bits[:]
        return s


class Port:
    def __init__(self, name: str, direction: str, width: int = 1):
        self.name = name
        self.direction = direction
        self.width = width
        self.signal = Signal(width=width)

    def __repr__(self) -> str:
        return f"Port({self.name}, {self.direction}, w={self.width})"


class Node:
    def __init__(self, node_id: str, node_type: str):
        self.id = node_id
        self.type = node_type
        self.inputs: Dict[str, Port] = {}
        self.outputs: Dict[str, Port] = {}
        self.params: Dict[str, Any] = {}
        self.evaluated = False

    def add_input(self, name: str, width: int = 1):
        self.inputs[name] = Port(name, 'in', width)

    def add_output(self, name: str, width: int = 1):
        self.outputs[name] = Port(name, 'out', width)

    def get_port(self, port_name: str) -> Optional[Port]:
        if port_name in self.inputs:
            return self.inputs[port_name]
        if port_name in self.outputs:
            return self.outputs[port_name]
        return None

    def is_sequential(self) -> bool:
        return False

    def is_edge_triggered(self) -> bool:
        return False

    def evaluate(self):
        pass

    def clock_edge(self):
        pass


class GateNode(Node):
    GATE_FUNCTIONS = {
        'AND': lambda bits: all(bits),
        'OR': lambda bits: any(bits),
        'NOT': lambda bits: 1 - bits[0],
        'NAND': lambda bits: 0 if all(bits) else 1,
        'NOR': lambda bits: 0 if any(bits) else 1,
        'XOR': lambda bits: sum(bits) % 2,
        'XNOR': lambda bits: 1 - (sum(bits) % 2),
    }

    def __init__(self, node_id: str, gate_type: str, num_inputs: int = 2):
        super().__init__(node_id, gate_type)
        if gate_type == 'NOT':
            num_inputs = 1
        self.num_inputs = num_inputs
        for i in range(num_inputs):
            self.add_input(f'in{i}')
        self.add_output('out')
        self.params['num_inputs'] = num_inputs

    def evaluate(self):
        bits = [self.inputs[f'in{i}'].signal[0] for i in range(self.num_inputs)]
        result = int(self.GATE_FUNCTIONS[self.type](bits))
        self.outputs['out'].signal[0] = result


class InputNode(Node):
    def __init__(self, node_id: str, width: int = 1):
        super().__init__(node_id, 'INPUT')
        self.add_output('out', width)
        self.params['width'] = width

    def set_value(self, value: SignalValue):
        if isinstance(value, Signal):
            self.outputs['out'].signal = value.copy()
        else:
            self.outputs['out'].signal = Signal(value, self.params['width'])


class OutputNode(Node):
    def __init__(self, node_id: str, width: int = 1):
        super().__init__(node_id, 'OUTPUT')
        self.add_input('in', width)
        self.params['width'] = width

    def get_value(self) -> Signal:
        return self.inputs['in'].signal.copy()


class ConstNode(Node):
    def __init__(self, node_id: str, value: int, width: int = 1):
        super().__init__(node_id, 'CONST')
        self.add_output('out', width)
        self.params['value'] = value
        self.params['width'] = width
        self.outputs['out'].signal = Signal(value, width)


class DFlipFlop(Node):
    def __init__(self, node_id: str, width: int = 1):
        super().__init__(node_id, 'DFF')
        self.add_input('D', width)
        self.add_output('Q', width)
        self.add_output('Qn', width)
        self.params['width'] = width
        self.state = Signal(width=width)
        self.next_state = Signal(width=width)
        for i in range(width):
            self.outputs['Q'].signal[i] = self.state[i]
            self.outputs['Qn'].signal[i] = 1 - self.state[i]

    def is_sequential(self) -> bool:
        return True

    def is_edge_triggered(self) -> bool:
        return True

    def evaluate(self):
        self.next_state = self.inputs['D'].signal.copy()

    def clock_edge(self):
        self.state = self.next_state.copy()
        w = self.params['width']
        for i in range(w):
            self.outputs['Q'].signal[i] = self.state[i]
            self.outputs['Qn'].signal[i] = 1 - self.state[i]


class SRLatch(Node):
    def __init__(self, node_id: str):
        super().__init__(node_id, 'SRLATCH')
        self.add_input('S')
        self.add_input('R')
        self.add_output('Q')
        self.add_output('Qn')
        self.state = 0
        self.outputs['Q'].signal[0] = self.state
        self.outputs['Qn'].signal[0] = 1 - self.state

    def is_sequential(self) -> bool:
        return True

    def evaluate(self):
        s = self.inputs['S'].signal[0]
        r = self.inputs['R'].signal[0]
        if s == 1 and r == 1:
            pass
        elif s == 1:
            self.state = 1
        elif r == 1:
            self.state = 0
        self.outputs['Q'].signal[0] = self.state
        self.outputs['Qn'].signal[0] = 1 - self.state


class Register(Node):
    def __init__(self, node_id: str, width: int = 4):
        super().__init__(node_id, 'REG')
        self.add_input('D', width)
        self.add_input('EN')
        self.add_output('Q', width)
        self.params['width'] = width
        self.state = Signal(width=width)
        self.next_state = Signal(width=width)
        for i in range(width):
            self.outputs['Q'].signal[i] = self.state[i]

    def is_sequential(self) -> bool:
        return True

    def is_edge_triggered(self) -> bool:
        return True

    def evaluate(self):
        en = self.inputs['EN'].signal[0]
        if en:
            self.next_state = self.inputs['D'].signal.copy()
        else:
            self.next_state = self.state.copy()

    def clock_edge(self):
        self.state = self.next_state.copy()
        w = self.params['width']
        for i in range(w):
            self.outputs['Q'].signal[i] = self.state[i]


class Wire:
    def __init__(self, src_node: str, src_port: str,
                 dst_pairs: List[Tuple[str, str]], width: int = 1):
        self.src_node = src_node
        self.src_port = src_port
        self.dst_pairs = dst_pairs
        self.width = width

    def __repr__(self) -> str:
        return f"Wire({self.src_node}.{self.src_port} -> {self.dst_pairs})"


# ============================================================
# 功能1：模块系统 - ModuleDefinition和ModuleRegistry
# ============================================================

class ModuleDefinition:
    def __init__(self, name: str, ports: List[Dict[str, Any]],
                 circuit_data: Dict[str, Any]):
        self.name = name.upper()
        self.ports = ports
        self.input_ports = [p for p in ports if p['direction'].lower() in ('in', 'input')]
        self.output_ports = [p for p in ports if p['direction'].lower() in ('out', 'output')]
        self.circuit_data = circuit_data

    def __repr__(self) -> str:
        in_names = [f"{p['name']}[{p.get('width', 1)}]" for p in self.input_ports]
        out_names = [f"{p['name']}[{p.get('width', 1)}]" for p in self.output_ports]
        return f"Module {self.name}: inputs=({', '.join(in_names)}), outputs=({', '.join(out_names)})"


class ModuleRegistry:
    def __init__(self):
        self.modules: Dict[str, ModuleDefinition] = {}

    def register(self, definition: ModuleDefinition):
        self.modules[definition.name] = definition

    def get(self, name: str) -> Optional[ModuleDefinition]:
        return self.modules.get(name.upper())

    def list_all(self) -> List[ModuleDefinition]:
        return list(self.modules.values())

    def define_from_json(self, name: str, filepath: str) -> ModuleDefinition:
        with open(filepath, 'r') as f:
            data = json.load(f)

        ports = data.get('ports', [])
        if not ports:
            raise ValueError(f"Module JSON must contain 'ports' declaration with input/output directions")

        circuit_data = {
            'nodes': data.get('nodes', []),
            'wires': data.get('wires', [])
        }

        definition = ModuleDefinition(name, ports, circuit_data)
        self.register(definition)
        return definition


GLOBAL_MODULE_REGISTRY = ModuleRegistry()


class ModuleInstance(Node):
    def __init__(self, node_id: str, module_name: str,
                 registry: Optional[ModuleRegistry] = None):
        super().__init__(node_id, 'MODULE')
        self.module_name = module_name.upper()
        self.registry = registry or GLOBAL_MODULE_REGISTRY
        self.definition = self.registry.get(self.module_name)
        if self.definition is None:
            raise ValueError(f"Module '{self.module_name}' not registered. Available: {list(self.registry.modules.keys())}")

        self.params['module'] = self.module_name

        self.internal_circuit: Optional[Circuit] = None

        for port_def in self.definition.input_ports:
            width = port_def.get('width', 1)
            self.add_input(port_def['name'], width)

        for port_def in self.definition.output_ports:
            width = port_def.get('width', 1)
            self.add_output(port_def['name'], width)

    def _instantiate_internal(self):
        self.internal_circuit = parse_circuit_from_json(
            self.definition.circuit_data, self.registry
        )

    def evaluate(self):
        if self.internal_circuit is None:
            self._instantiate_internal()

        for port_def in self.definition.input_ports:
            port_name = port_def['name']
            width = port_def.get('width', 1)
            input_signal = self.inputs[port_name].signal.copy()
            self.internal_circuit.set_input(port_name, input_signal)

        self.internal_circuit.evaluate_combinational()

        for port_def in self.definition.output_ports:
            port_name = port_def['name']
            output_signal = self.internal_circuit.get_output(port_name)
            self.outputs[port_name].signal = output_signal.copy()


# ============================================================
# 功能2：故障注入系统
# ============================================================

class Fault:
    pass


class StuckAtFault(Fault):
    def __init__(self, node_id: str, port_name: str, value: int):
        self.node_id = node_id
        self.port_name = port_name
        self.value = value & 1
        self.fault_type = f'stuck-at-{self.value}'

    def describe(self) -> str:
        return f"StuckAtFault: {self.node_id}.{self.port_name} = {self.value} (stuck-at-{self.value})"

    def apply(self, circuit: 'Circuit'):
        node = circuit.nodes.get(self.node_id)
        if node is None:
            return
        port = node.get_port(self.port_name)
        if port is None:
            return
        for i in range(port.width):
            port.signal[i] = self.value


class BridgeFault(Fault):
    def __init__(self, node1_id: str, port1_name: str,
                 node2_id: str, port2_name: str):
        self.node1_id = node1_id
        self.port1_name = port1_name
        self.node2_id = node2_id
        self.port2_name = port2_name
        self.fault_type = 'bridge-OR'

    def describe(self) -> str:
        return (f"BridgeFault(OR): {self.node1_id}.{self.port1_name} || "
                f"{self.node2_id}.{self.port2_name}")

    def apply(self, circuit: 'Circuit'):
        node1 = circuit.nodes.get(self.node1_id)
        node2 = circuit.nodes.get(self.node2_id)
        if node1 is None or node2 is None:
            return
        port1 = node1.get_port(self.port1_name)
        port2 = node2.get_port(self.port2_name)
        if port1 is None or port2 is None:
            return
        min_w = min(port1.width, port2.width)
        for i in range(min_w):
            bridged = port1.signal[i] | port2.signal[i]
            port1.signal[i] = bridged
            port2.signal[i] = bridged


class FaultManager:
    def __init__(self):
        self.faults: List[Fault] = []

    def add_stuck_at(self, node_id: str, port_name: str, value: int):
        self.faults.append(StuckAtFault(node_id, port_name, value))

    def add_bridge(self, node1: str, port1: str, node2: str, port2: str):
        self.faults.append(BridgeFault(node1, port1, node2, port2))

    def list_faults(self) -> List[str]:
        return [f"[{i}] {f.describe()}" for i, f in enumerate(self.faults)]

    def clear(self):
        self.faults.clear()

    def apply_stuck_at_faults(self, circuit: 'Circuit'):
        for fault in self.faults:
            if isinstance(fault, StuckAtFault):
                fault.apply(circuit)

    def apply_bridge_faults(self, circuit: 'Circuit'):
        for fault in self.faults:
            if isinstance(fault, BridgeFault):
                fault.apply(circuit)

    def apply_all(self, circuit: 'Circuit'):
        for fault in self.faults:
            fault.apply(circuit)


# ============================================================
# 功能3：时序分析系统
# ============================================================

GATE_DELAYS: Dict[str, float] = {
    'AND': 2.0,
    'OR': 2.0,
    'NOT': 1.0,
    'NAND': 2.0,
    'NOR': 2.0,
    'XOR': 3.0,
    'XNOR': 3.0,
    'CONST': 0.0,
    'INPUT': 0.0,
    'OUTPUT': 0.0,
    'DFF': 1.0,
    'REG': 1.0,
    'SRLATCH': 1.0,
    'MODULE': 0.0,
}


def get_gate_delay(gate_type: str) -> float:
    return GATE_DELAYS.get(gate_type.upper(), 2.0)


class TimingResult:
    def __init__(self, input_name: str, output_name: str,
                 delay: float, path: List[str]):
        self.input_name = input_name
        self.output_name = output_name
        self.delay = delay
        self.path = path

    def describe(self) -> str:
        path_str = ' -> '.join(self.path)
        return (f"{self.input_name} -> {self.output_name}: "
                f"{self.delay:.1f}ns, path: [{path_str}]")


class TimingAnalyzer:
    def __init__(self, circuit: 'Circuit',
                 gate_delays: Optional[Dict[str, float]] = None):
        self.circuit = circuit
        self.delays = dict(gate_delays) if gate_delays else dict(GATE_DELAYS)

    def set_delay(self, gate_type: str, delay: float):
        self.delays[gate_type.upper()] = delay

    def _get_node_delay(self, node: Node) -> float:
        if node.type == 'MODULE':
            mod_total = 0.0
            if hasattr(node, 'internal_circuit') and node.internal_circuit:
                sub_analyzer = TimingAnalyzer(node.internal_circuit, self.delays)
                results = sub_analyzer.analyze_all_paths()
                if results:
                    mod_total = max(r.delay for r in results)
            return mod_total
        return self.delays.get(node.type.upper(), 2.0)

    def _build_graph(self) -> Tuple[Dict[str, List[Tuple[str, str]]],
                                    Dict[str, int]]:
        adj = defaultdict(list)
        in_degree = defaultdict(int)
        node_ids = set()

        for wire in self.circuit.wires:
            src = wire.src_node
            src_node = self.circuit.nodes.get(src)
            if src_node and src_node.is_sequential():
                continue
            for dst_id, _ in wire.dst_pairs:
                dst_node = self.circuit.nodes.get(dst_id)
                if dst_node and dst_node.is_sequential():
                    continue
                adj[src].append((dst_id, wire.src_port))
                in_degree[dst_id] += 1
                node_ids.add(src)
                node_ids.add(dst_id)

        for nid in self.circuit.nodes:
            if nid not in node_ids:
                node_ids.add(nid)
                if nid not in in_degree:
                    in_degree[nid] = 0

        return adj, in_degree, node_ids

    def topological_sort(self) -> List[str]:
        adj, in_degree, node_ids = self._build_graph()
        queue = deque()
        for nid in sorted(node_ids):
            if in_degree.get(nid, 0) == 0:
                queue.append(nid)

        order = []
        while queue:
            nid = queue.popleft()
            order.append(nid)
            for neighbor, _ in adj.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        return order

    def analyze_all_paths(self) -> List[TimingResult]:
        adj, in_degree, node_ids = self._build_graph()
        topo_order = self.topological_sort()

        arrival = {}
        predecessor = {}

        for nid in topo_order:
            arrival[nid] = (0.0, None)
            predecessor[nid] = None

        for nid in topo_order:
            node = self.circuit.nodes.get(nid)
            if node is None:
                continue
            cur_delay, _ = arrival[nid]
            node_delay = self._get_node_delay(node)
            total_delay = cur_delay + node_delay

            for neighbor, _ in adj.get(nid, []):
                if neighbor not in arrival or total_delay > arrival[neighbor][0]:
                    arrival[neighbor] = (total_delay, nid)

        results = []
        for inp_id in sorted(self.circuit.input_nodes.keys()):
            for out_id in sorted(self.circuit.output_nodes.keys()):
                delay_from_input, path_end = self._trace_path_delay(
                    inp_id, out_id, adj, arrival)
                if path_end is not None or delay_from_input > 0:
                    path = self._reconstruct_path(inp_id, out_id, arrival)
                    results.append(TimingResult(inp_id, out_id,
                                                delay_from_input, path))

        return sorted(results, key=lambda r: -r.delay)

    def _trace_path_delay(self, input_id: str, output_id: str,
                          adj, arrival) -> Tuple[float, Optional[str]]:
        visited = set()
        stack = [(input_id, 0.0)]
        max_delay = 0.0
        reachable = False

        while stack:
            nid, cur_d = stack.pop()
            if nid in visited:
                continue
            visited.add(nid)

            if nid == output_id:
                reachable = True
                max_delay = max(max_delay, cur_d)

            node = self.circuit.nodes.get(nid)
            node_delay = self._get_node_delay(node) if node else 0.0
            next_d = cur_d + node_delay

            for neighbor, _ in adj.get(nid, []):
                if neighbor not in visited:
                    stack.append((neighbor, next_d))

        return (max_delay, output_id) if reachable else (0.0, None)

    def _reconstruct_path(self, input_id: str, output_id: str,
                          arrival) -> List[str]:
        if output_id not in self.circuit.nodes:
            return [input_id, output_id]

        adj, _, _ = self._build_graph()
        best_path = [input_id]
        best_delay = -1

        def dfs(cur_id, path, delay):
            nonlocal best_path, best_delay
            if cur_id == output_id:
                if delay > best_delay:
                    best_delay = delay
                    best_path = list(path)
                return
            node = self.circuit.nodes.get(cur_id)
            node_delay = self._get_node_delay(node) if node else 0.0
            for neighbor, _ in adj.get(cur_id, []):
                if neighbor not in path:
                    path.append(neighbor)
                    dfs(neighbor, path, delay + node_delay)
                    path.pop()

        dfs(input_id, [input_id], 0.0)
        return best_path

    def find_critical_path(self) -> Optional[TimingResult]:
        results = self.analyze_all_paths()
        if not results:
            return None
        return results[0]

    def generate_report(self, clock_period_ns: Optional[float] = None) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append("TIMING ANALYSIS REPORT")
        lines.append("=" * 70)

        lines.append(f"\nGate Delays (ns):")
        for gt in sorted(self.delays.keys()):
            lines.append(f"  {gt:<10}: {self.delays[gt]:.1f}")

        results = self.analyze_all_paths()
        lines.append(f"\nPath Analysis ({len(results)} paths):")
        lines.append("-" * 70)
        lines.append(f"  {'Input':<10} {'Output':<10} {'Delay(ns)':<10} Path")
        lines.append("-" * 70)
        for r in results:
            path_str = ' -> '.join(r.path)
            lines.append(f"  {r.input_name:<10} {r.output_name:<10} "
                         f"{r.delay:<10.1f} {path_str}")

        critical = self.find_critical_path()
        if critical:
            lines.append(f"\nCRITICAL PATH:")
            lines.append(f"  {'Input':<10}: {critical.input_name}")
            lines.append(f"  {'Output':<10}: {critical.output_name}")
            lines.append(f"  {'Total Delay':<10}: {critical.delay:.1f} ns")
            lines.append(f"  {'Path':<10}: {' -> '.join(critical.path)}")

            if clock_period_ns is not None:
                lines.append(f"\nTiming Check (Clock Period = {clock_period_ns:.1f} ns):")
                setup_slack = clock_period_ns - critical.delay
                hold_slack = critical.delay
                lines.append(f"  {'Setup Slack':<15}: {setup_slack:.1f} ns "
                             f"({'PASS' if setup_slack >= 0 else 'FAIL'})")
                lines.append(f"  {'Hold Slack':<15}: {hold_slack:.1f} ns "
                             f"({'PASS' if hold_slack > 0 else 'FAIL'})")

                lines.append(f"\nPer-Output Arrival Times:")
                output_arrivals = defaultdict(float)
                for r in results:
                    output_arrivals[r.output_name] = max(
                        output_arrivals[r.output_name], r.delay)
                for out_id in sorted(output_arrivals.keys()):
                    arr = output_arrivals[out_id]
                    s_slack = clock_period_ns - arr
                    h_slack = arr
                    lines.append(f"  {out_id:<10}: arrival={arr:.1f}ns, "
                                 f"setup_slack={s_slack:.1f}ns, "
                                 f"hold_slack={h_slack:.1f}ns")

        lines.append("\n" + "=" * 70)
        return '\n'.join(lines)


# ============================================================
# ATPG (自动测试模式生成)
# ============================================================

class ATPG:
    def __init__(self, circuit: 'Circuit', registry: Optional[ModuleRegistry] = None):
        self.circuit = circuit
        self.registry = registry or GLOBAL_MODULE_REGISTRY
        self.input_names = sorted(circuit.input_nodes.keys())
        self.output_names = sorted(circuit.output_nodes.keys())

    def _simulate_with_inputs(self, inputs_dict: Dict[str, int]) -> Dict[str, Signal]:
        sim_circuit = parse_circuit_from_json(
            self._circuit_to_json(), self.registry)
        for name, val in inputs_dict.items():
            if name in sim_circuit.input_nodes:
                sim_circuit.set_input(name, val)
        sim_circuit.evaluate_combinational()
        outputs = {}
        for out_name in self.output_names:
            if out_name in sim_circuit.output_nodes:
                outputs[out_name] = sim_circuit.get_output(out_name)
        return outputs

    def _simulate_with_fault(self, inputs_dict: Dict[str, int],
                             fault: Fault) -> Dict[str, Signal]:
        sim_circuit = parse_circuit_from_json(
            self._circuit_to_json(), self.registry)
        for name, val in inputs_dict.items():
            if name in sim_circuit.input_nodes:
                sim_circuit.set_input(name, val)

        sim_circuit.fault_manager.faults.append(fault)

        sim_circuit.evaluate_combinational()

        outputs = {}
        for out_name in self.output_names:
            if out_name in sim_circuit.output_nodes:
                outputs[out_name] = sim_circuit.get_output(out_name)
        return outputs

    def _circuit_to_json(self) -> Dict[str, Any]:
        nodes_json = []
        for nid, node in self.circuit.nodes.items():
            node_json = {
                'type': node.type,
                'id': node.id,
                'params': node.params.copy()
            }
            if node.type == 'MODULE':
                node_json['module'] = node.module_name
            nodes_json.append(node_json)

        wires_json = []
        for w in self.circuit.wires:
            src_str = f"{w.src_node}.{w.src_port}"
            dst_list = [f"{dn}.{dp}" for dn, dp in w.dst_pairs]
            wires_json.append({'src': src_str, 'dst': dst_list, 'width': w.width})

        return {'nodes': nodes_json, 'wires': wires_json}

    def generate_for_stuck_at(self, node_id: str, port_name: str,
                              stuck_value: int,
                              max_inputs: int = 16):
        n_inputs = len(self.input_names)
        if n_inputs > max_inputs:
            return None

        target_fault = StuckAtFault(node_id, port_name, stuck_value)

        for combo in itertools.product([0, 1], repeat=n_inputs):
            input_dict = dict(zip(self.input_names, combo))

            good_outputs = self._simulate_with_inputs(input_dict)
            bad_outputs = self._simulate_with_fault(input_dict, target_fault)

            detected = False
            diff_outputs = {}
            for out_name in self.output_names:
                g = good_outputs.get(out_name)
                b = bad_outputs.get(out_name)
                if g and b and g != b:
                    detected = True
                    diff_outputs[out_name] = (g, b)

            if detected:
                return {
                    'inputs': input_dict,
                    'detected': True,
                    'differences': diff_outputs,
                    'good_outputs': good_outputs,
                    'bad_outputs': bad_outputs,
                }

        return {
            'inputs': None,
            'detected': False,
            'differences': {},
            'good_outputs': {},
            'bad_outputs': {},
        }

    def generate_for_bridge(self, node1_id: str, port1_name: str,
                            node2_id: str, port2_name: str,
                            max_inputs: int = 16):
        n_inputs = len(self.input_names)
        if n_inputs > max_inputs:
            return None

        target_fault = BridgeFault(node1_id, port1_name,
                                   node2_id, port2_name)

        for combo in itertools.product([0, 1], repeat=n_inputs):
            input_dict = dict(zip(self.input_names, combo))

            good_outputs = self._simulate_with_inputs(input_dict)
            bad_outputs = self._simulate_with_fault(input_dict, target_fault)

            detected = False
            diff_outputs = {}
            for out_name in self.output_names:
                g = good_outputs.get(out_name)
                b = bad_outputs.get(out_name)
                if g and b and g != b:
                    detected = True
                    diff_outputs[out_name] = (g, b)

            if detected:
                return {
                    'inputs': input_dict,
                    'detected': True,
                    'differences': diff_outputs,
                    'good_outputs': good_outputs,
                    'bad_outputs': bad_outputs,
                }

        return {
            'inputs': None,
            'detected': False,
            'differences': {},
            'good_outputs': {},
            'bad_outputs': {},
        }


# ============================================================
# Circuit 类（扩展支持故障注入、模块实例）
# ============================================================

class Circuit:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.wires: List[Wire] = []
        self.input_nodes: Dict[str, InputNode] = {}
        self.output_nodes: Dict[str, OutputNode] = {}
        self.sequential_nodes: List[Node] = []
        self.fault_manager = FaultManager()

    def add_node(self, node: Node):
        self.nodes[node.id] = node
        if isinstance(node, InputNode):
            self.input_nodes[node.id] = node
        elif isinstance(node, OutputNode):
            self.output_nodes[node.id] = node
        if node.is_sequential():
            self.sequential_nodes.append(node)

    def add_wire(self, wire: Wire):
        self.wires.append(wire)

    def propagate(self, wire: Wire):
        src_node = self.nodes[wire.src_node]
        src_port = src_node.get_port(wire.src_port)
        if src_port is None:
            raise ValueError(f"Port {wire.src_port} not found on node {wire.src_node}")

        for dst_node_id, dst_port_name in wire.dst_pairs:
            dst_node = self.nodes.get(dst_node_id)
            if dst_node is None:
                raise ValueError(f"Destination node {dst_node_id} not found")
            dst_port = dst_node.get_port(dst_port_name)
            if dst_port is None:
                raise ValueError(f"Port {dst_port_name} not found on node {dst_node_id}")
            if src_port.width != dst_port.width:
                raise ValueError(
                    f"Width mismatch: {wire.src_node}.{wire.src_port}({src_port.width}) "
                    f"-> {dst_node_id}.{dst_port_name}({dst_port.width})"
                )
            for i in range(src_port.width):
                dst_port.signal[i] = src_port.signal[i]

    def detect_combinational_loops(self) -> List[List[str]]:
        adj = defaultdict(list)
        in_degree = defaultdict(int)
        node_ids = set()

        for wire in self.wires:
            src = wire.src_node
            src_node = self.nodes.get(src)
            if src_node and src_node.is_sequential():
                continue
            for dst_id, _ in wire.dst_pairs:
                dst_node = self.nodes.get(dst_id)
                if dst_node and dst_node.is_sequential():
                    continue
                adj[src].append(dst_id)
                in_degree[dst_id] += 1
                node_ids.add(src)
                node_ids.add(dst_id)

        queue = deque()
        for nid in node_ids:
            if in_degree[nid] == 0:
                queue.append(nid)

        visited_count = 0
        order = []
        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            visited_count += 1
            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count == len(node_ids):
            return []

        loops = []
        visited = set()
        for nid in node_ids:
            if nid not in visited and in_degree[nid] > 0:
                path = []
                self._find_loop_dfs(nid, adj, visited, path, set(), loops)
        return loops

    def _find_loop_dfs(self, node_id, adj, visited, path, path_set, loops):
        if node_id in path_set:
            start_idx = path.index(node_id)
            loops.append(path[start_idx:] + [node_id])
            return
        if node_id in visited:
            return
        visited.add(node_id)
        path.append(node_id)
        path_set.add(node_id)
        for neighbor in adj.get(node_id, []):
            self._find_loop_dfs(neighbor, adj, visited, path, path_set, loops)
        path.pop()
        path_set.discard(node_id)

    def evaluate_combinational(self, max_iterations: int = 1000) -> int:
        loops = self.detect_combinational_loops()
        if loops:
            loop_str = ' -> '.join(loops[0])
            raise ValueError(f"Combinational loop detected: {loop_str}")

        iterations = 0
        for node in self.nodes.values():
            node.evaluated = False

        bridge_port_keys = set()
        for fault in self.fault_manager.faults:
            if isinstance(fault, BridgeFault):
                bridge_port_keys.add((fault.node1_id, fault.port1_name))
                bridge_port_keys.add((fault.node2_id, fault.port2_name))

        prev_output_snapshot = None

        while iterations < max_iterations:
            iterations += 1
            changed = False

            for node in self.nodes.values():
                if node.is_edge_triggered():
                    continue
                node.evaluate()

            self.fault_manager.apply_stuck_at_faults(self)

            for wire in self.wires:
                src_node = self.nodes[wire.src_node]
                src_port = src_node.get_port(wire.src_port)
                if src_port is None:
                    continue
                for dst_node_id, dst_port_name in wire.dst_pairs:
                    dst_node = self.nodes.get(dst_node_id)
                    if dst_node is None:
                        continue
                    dst_port = dst_node.get_port(dst_port_name)
                    if dst_port is None:
                        continue
                    for i in range(src_port.width):
                        if dst_port.signal[i] != src_port.signal[i]:
                            dst_port.signal[i] = src_port.signal[i]
                            if (dst_node_id, dst_port_name) not in bridge_port_keys:
                                changed = True

            self.fault_manager.apply_bridge_faults(self)

            cur_output_snapshot = {}
            for nid, node in self.nodes.items():
                for pname, port in node.outputs.items():
                    cur_output_snapshot[(nid, pname)] = port.signal.bits[:]

            if not changed:
                if prev_output_snapshot is not None and cur_output_snapshot == prev_output_snapshot:
                    break
                if not self.fault_manager.faults:
                    break

            prev_output_snapshot = cur_output_snapshot

        self.fault_manager.apply_stuck_at_faults(self)

        return iterations

    def run_clock(self):
        self.evaluate_combinational()
        for node in self.sequential_nodes:
            node.evaluate()
        for node in self.sequential_nodes:
            node.clock_edge()
        self.evaluate_combinational()

    def set_input(self, name: str, value: SignalValue):
        if name not in self.input_nodes:
            raise ValueError(f"Input '{name}' not found. Available: {list(self.input_nodes.keys())}")
        self.input_nodes[name].set_value(value)

    def get_output(self, name: str) -> Signal:
        if name not in self.output_nodes:
            raise ValueError(f"Output '{name}' not found. Available: {list(self.output_nodes.keys())}")
        return self.output_nodes[name].get_value()

    def get_signal_value(self, node_id: str, port_name: str) -> Optional[Signal]:
        node = self.nodes.get(node_id)
        if node is None:
            return None
        port = node.get_port(port_name)
        if port is None:
            return None
        return port.signal.copy()


# ============================================================
# JSON 解析（扩展支持 module 类型）
# ============================================================

def parse_circuit_from_json(data: Dict[str, Any],
                            registry: Optional[ModuleRegistry] = None
                            ) -> Circuit:
    registry = registry or GLOBAL_MODULE_REGISTRY
    circuit = Circuit()

    for node_data in data.get('nodes', []):
        node = create_node_from_json(node_data, registry)
        circuit.add_node(node)

    for wire_data in data.get('wires', []):
        wire = create_wire_from_json(wire_data, data.get('nodes', []))
        circuit.add_wire(wire)

    return circuit


def create_node_from_json(node_data: Dict[str, Any],
                          registry: Optional[ModuleRegistry] = None
                          ) -> Node:
    registry = registry or GLOBAL_MODULE_REGISTRY
    node_type = node_data.get('type', '').upper()
    node_id = node_data.get('id', '')
    params = node_data.get('params', {})
    width = int(params.get('width', 1))

    if node_type == 'INPUT':
        node = InputNode(node_id, width)
    elif node_type == 'OUTPUT':
        node = OutputNode(node_id, width)
    elif node_type == 'CONST':
        value = int(params.get('value', 0))
        node = ConstNode(node_id, value, width)
    elif node_type in ['AND', 'OR', 'NOT', 'NAND', 'NOR', 'XOR', 'XNOR']:
        num_inputs = int(params.get('num_inputs', 2))
        node = GateNode(node_id, node_type, num_inputs)
    elif node_type == 'DFF':
        node = DFlipFlop(node_id, width)
    elif node_type == 'SRLATCH':
        node = SRLatch(node_id)
    elif node_type == 'REG':
        node = Register(node_id, width)
    elif node_type == 'MODULE':
        module_name = node_data.get('module', params.get('module', ''))
        node = ModuleInstance(node_id, module_name, registry)
    else:
        raise ValueError(f"Unknown node type: {node_type}")

    return node


def create_wire_from_json(wire_data: Dict[str, Any],
                          nodes_data: List[Dict[str, Any]] = []) -> Wire:
    src = wire_data.get('src', '')
    if '.' in src:
        src_node, src_port = src.split('.', 1)
    else:
        src_node = src
        src_port = 'out'

    dst = wire_data.get('dst', [])
    dst_pairs = []
    if isinstance(dst, str):
        dst = [dst]
    for d in dst:
        if '.' in d:
            dst_node, dst_port = d.split('.', 1)
        else:
            dst_node = d
            dst_port = 'in'
        dst_pairs.append((dst_node, dst_port))

    width = int(wire_data.get('width', 1))
    return Wire(src_node, src_port, dst_pairs, width)


# ============================================================
# 预设电路
# ============================================================

def create_ripple_carry_adder_4bit() -> Dict[str, Any]:
    nodes = []
    wires = []

    for i in range(4):
        nodes.append({'type': 'INPUT', 'id': f'A{i}', 'params': {'width': 1}})
        nodes.append({'type': 'INPUT', 'id': f'B{i}', 'params': {'width': 1}})
    nodes.append({'type': 'INPUT', 'id': 'Cin', 'params': {'width': 1}})

    nodes.append({'type': 'OUTPUT', 'id': 'S0', 'params': {'width': 1}})
    nodes.append({'type': 'OUTPUT', 'id': 'S1', 'params': {'width': 1}})
    nodes.append({'type': 'OUTPUT', 'id': 'S2', 'params': {'width': 1}})
    nodes.append({'type': 'OUTPUT', 'id': 'S3', 'params': {'width': 1}})
    nodes.append({'type': 'OUTPUT', 'id': 'Cout', 'params': {'width': 1}})

    for i in range(4):
        nodes.append({'type': 'XOR', 'id': f'xor1_{i}'})
        nodes.append({'type': 'XOR', 'id': f'xor2_{i}'})
        nodes.append({'type': 'AND', 'id': f'and1_{i}'})
        nodes.append({'type': 'AND', 'id': f'and2_{i}'})
        nodes.append({'type': 'OR', 'id': f'or1_{i}'})

    wires.append({'src': 'Cin', 'dst': [f'xor2_0.in1', f'and2_0.in1']})

    for i in range(4):
        wires.append({'src': f'A{i}', 'dst': [f'xor1_{i}.in0', f'and1_{i}.in0']})
        wires.append({'src': f'B{i}', 'dst': [f'xor1_{i}.in1', f'and1_{i}.in1']})
        wires.append({'src': f'xor1_{i}.out', 'dst': [f'xor2_{i}.in0', f'and2_{i}.in0']})
        wires.append({'src': f'xor2_{i}.out', 'dst': [f'S{i}.in']})
        wires.append({'src': f'and1_{i}.out', 'dst': [f'or1_{i}.in0']})
        wires.append({'src': f'and2_{i}.out', 'dst': [f'or1_{i}.in1']})

        if i < 3:
            wires.append({'src': f'or1_{i}.out', 'dst': [f'xor2_{i+1}.in1', f'and2_{i+1}.in1']})
        else:
            wires.append({'src': f'or1_{i}.out', 'dst': ['Cout.in']})

    return {'nodes': nodes, 'wires': wires}


def create_shift_register_8bit() -> Dict[str, Any]:
    nodes = []
    wires = []

    nodes.append({'type': 'INPUT', 'id': 'CLK', 'params': {'width': 1}})
    nodes.append({'type': 'INPUT', 'id': 'DATA_IN', 'params': {'width': 1}})
    nodes.append({'type': 'INPUT', 'id': 'EN', 'params': {'width': 1}})

    for i in range(8):
        nodes.append({'type': 'OUTPUT', 'id': f'Q{i}', 'params': {'width': 1}})

    for i in range(8):
        nodes.append({'type': 'DFF', 'id': f'dff{i}', 'params': {'width': 1}})

    nodes.append({'type': 'NOT', 'id': 'not_en'})
    wires.append({'src': 'EN', 'dst': ['not_en.in0']})

    for i in range(8):
        nodes.append({'type': 'AND', 'id': f'and_shift{i}'})
        nodes.append({'type': 'AND', 'id': f'and_hold{i}'})
        nodes.append({'type': 'OR', 'id': f'or_mux{i}'})

        wires.append({'src': 'not_en.out', 'dst': [f'and_hold{i}.in1']})
        wires.append({'src': f'dff{i}.Q', 'dst': [f'and_hold{i}.in0']})

        wires.append({'src': 'EN', 'dst': [f'and_shift{i}.in1']})
        if i == 0:
            wires.append({'src': 'DATA_IN', 'dst': [f'and_shift{i}.in0']})
        else:
            wires.append({'src': f'dff{i-1}.Q', 'dst': [f'and_shift{i}.in0']})

        wires.append({'src': f'and_shift{i}.out', 'dst': [f'or_mux{i}.in0']})
        wires.append({'src': f'and_hold{i}.out', 'dst': [f'or_mux{i}.in1']})
        wires.append({'src': f'or_mux{i}.out', 'dst': [f'dff{i}.D']})

    for i in range(8):
        wires.append({'src': f'dff{i}.Q', 'dst': [f'Q{i}.in']})

    return {'nodes': nodes, 'wires': wires}


def create_decoder_3to8() -> Dict[str, Any]:
    nodes = []
    wires = []

    for i in range(3):
        nodes.append({'type': 'INPUT', 'id': f'A{i}', 'params': {'width': 1}})
    nodes.append({'type': 'INPUT', 'id': 'EN', 'params': {'width': 1}})

    for i in range(8):
        nodes.append({'type': 'OUTPUT', 'id': f'Y{i}', 'params': {'width': 1}})

    for i in range(3):
        nodes.append({'type': 'NOT', 'id': f'not_a{i}'})
        wires.append({'src': f'A{i}', 'dst': [f'not_a{i}.in0']})

    for y in range(8):
        nodes.append({'type': 'AND', 'id': f'and_y{y}', 'params': {'num_inputs': 4}})
        inputs = []
        for bit in range(3):
            if (y >> bit) & 1:
                inputs.append(f'A{bit}')
            else:
                inputs.append(f'not_a{bit}.out')
        inputs.append('EN')

        for idx, src in enumerate(inputs):
            wires.append({'src': src, 'dst': [f'and_y{y}.in{idx}']})
        wires.append({'src': f'and_y{y}.out', 'dst': [f'Y{y}.in']})

    return {'nodes': nodes, 'wires': wires}


def create_counter_4bit() -> Dict[str, Any]:
    nodes = []
    wires = []

    nodes.append({'type': 'INPUT', 'id': 'CLK', 'params': {'width': 1}})
    nodes.append({'type': 'INPUT', 'id': 'RST', 'params': {'width': 1}})
    nodes.append({'type': 'INPUT', 'id': 'EN', 'params': {'width': 1}})

    for i in range(4):
        nodes.append({'type': 'OUTPUT', 'id': f'Q{i}', 'params': {'width': 1}})
    nodes.append({'type': 'OUTPUT', 'id': 'COUT', 'params': {'width': 1}})

    for i in range(4):
        nodes.append({'type': 'DFF', 'id': f'dff{i}', 'params': {'width': 1}})
        nodes.append({'type': 'XOR', 'id': f'xor_toggle{i}'})

    nodes.append({'type': 'AND', 'id': 'and_toggle1'})
    nodes.append({'type': 'AND', 'id': 'and_toggle2', 'params': {'num_inputs': 3}})
    nodes.append({'type': 'AND', 'id': 'and_toggle3', 'params': {'num_inputs': 4}})
    nodes.append({'type': 'AND', 'id': 'and_cout', 'params': {'num_inputs': 5}})

    wires.append({'src': 'EN', 'dst': ['xor_toggle0.in1']})
    wires.append({'src': 'dff0.Q', 'dst': ['xor_toggle0.in0']})
    wires.append({'src': 'xor_toggle0.out', 'dst': ['dff0.D']})

    wires.append({'src': 'dff0.Q', 'dst': ['and_toggle1.in0']})
    wires.append({'src': 'EN', 'dst': ['and_toggle1.in1']})
    wires.append({'src': 'and_toggle1.out', 'dst': ['xor_toggle1.in1']})
    wires.append({'src': 'dff1.Q', 'dst': ['xor_toggle1.in0']})
    wires.append({'src': 'xor_toggle1.out', 'dst': ['dff1.D']})

    wires.append({'src': 'dff0.Q', 'dst': ['and_toggle2.in0']})
    wires.append({'src': 'dff1.Q', 'dst': ['and_toggle2.in1']})
    wires.append({'src': 'EN', 'dst': ['and_toggle2.in2']})
    wires.append({'src': 'and_toggle2.out', 'dst': ['xor_toggle2.in1']})
    wires.append({'src': 'dff2.Q', 'dst': ['xor_toggle2.in0']})
    wires.append({'src': 'xor_toggle2.out', 'dst': ['dff2.D']})

    wires.append({'src': 'dff0.Q', 'dst': ['and_toggle3.in0']})
    wires.append({'src': 'dff1.Q', 'dst': ['and_toggle3.in1']})
    wires.append({'src': 'dff2.Q', 'dst': ['and_toggle3.in2']})
    wires.append({'src': 'EN', 'dst': ['and_toggle3.in3']})
    wires.append({'src': 'and_toggle3.out', 'dst': ['xor_toggle3.in1']})
    wires.append({'src': 'dff3.Q', 'dst': ['xor_toggle3.in0']})
    wires.append({'src': 'xor_toggle3.out', 'dst': ['dff3.D']})

    wires.append({'src': 'dff0.Q', 'dst': ['and_cout.in0', 'Q0.in']})
    wires.append({'src': 'dff1.Q', 'dst': ['and_cout.in1', 'Q1.in']})
    wires.append({'src': 'dff2.Q', 'dst': ['and_cout.in2', 'Q2.in']})
    wires.append({'src': 'dff3.Q', 'dst': ['and_cout.in3', 'Q3.in']})
    wires.append({'src': 'EN', 'dst': ['and_cout.in4']})
    wires.append({'src': 'and_cout.out', 'dst': ['COUT.in']})

    return {'nodes': nodes, 'wires': wires}


PRESET_CIRCUITS = {
    'adder4': create_ripple_carry_adder_4bit,
    'shiftreg8': create_shift_register_8bit,
    'decoder3to8': create_decoder_3to8,
    'counter4': create_counter_4bit,
}


# ============================================================
# 模块示例电路 JSON 生成器（用于导出到文件）
# ============================================================

def create_halfadder_module_json() -> Dict[str, Any]:
    return {
        "ports": [
            {"name": "A", "direction": "input", "width": 1},
            {"name": "B", "direction": "input", "width": 1},
            {"name": "Sum", "direction": "output", "width": 1},
            {"name": "Cout", "direction": "output", "width": 1},
        ],
        "nodes": [
            {"type": "INPUT", "id": "A", "params": {"width": 1}},
            {"type": "INPUT", "id": "B", "params": {"width": 1}},
            {"type": "OUTPUT", "id": "Sum", "params": {"width": 1}},
            {"type": "OUTPUT", "id": "Cout", "params": {"width": 1}},
            {"type": "XOR", "id": "xor_sum", "params": {"num_inputs": 2}},
            {"type": "AND", "id": "and_cout", "params": {"num_inputs": 2}},
        ],
        "wires": [
            {"src": "A", "dst": ["xor_sum.in0", "and_cout.in0"]},
            {"src": "B", "dst": ["xor_sum.in1", "and_cout.in1"]},
            {"src": "xor_sum.out", "dst": ["Sum.in"]},
            {"src": "and_cout.out", "dst": ["Cout.in"]},
        ]
    }


def create_fulladder_module_json() -> Dict[str, Any]:
    return {
        "ports": [
            {"name": "A", "direction": "input", "width": 1},
            {"name": "B", "direction": "input", "width": 1},
            {"name": "Cin", "direction": "input", "width": 1},
            {"name": "Sum", "direction": "output", "width": 1},
            {"name": "Cout", "direction": "output", "width": 1},
        ],
        "nodes": [
            {"type": "INPUT", "id": "A", "params": {"width": 1}},
            {"type": "INPUT", "id": "B", "params": {"width": 1}},
            {"type": "INPUT", "id": "Cin", "params": {"width": 1}},
            {"type": "OUTPUT", "id": "Sum", "params": {"width": 1}},
            {"type": "OUTPUT", "id": "Cout", "params": {"width": 1}},
            {"type": "module", "id": "ha1", "module": "HALFADD"},
            {"type": "module", "id": "ha2", "module": "HALFADD"},
            {"type": "OR", "id": "or_cout", "params": {"num_inputs": 2}},
        ],
        "wires": [
            {"src": "A", "dst": ["ha1.A"]},
            {"src": "B", "dst": ["ha1.B"]},
            {"src": "ha1.Sum", "dst": ["ha2.A"]},
            {"src": "Cin", "dst": ["ha2.B"]},
            {"src": "ha2.Sum", "dst": ["Sum.in"]},
            {"src": "ha1.Cout", "dst": ["or_cout.in0"]},
            {"src": "ha2.Cout", "dst": ["or_cout.in1"]},
            {"src": "or_cout.out", "dst": ["Cout.in"]},
        ]
    }


def create_adder4_module_json() -> Dict[str, Any]:
    nodes = []
    wires = []

    for i in range(4):
        nodes.append({"type": "INPUT", "id": f"A{i}", "params": {"width": 1}})
        nodes.append({"type": "INPUT", "id": f"B{i}", "params": {"width": 1}})
    nodes.append({"type": "INPUT", "id": "Cin", "params": {"width": 1}})

    for i in range(4):
        nodes.append({"type": "OUTPUT", "id": f"S{i}", "params": {"width": 1}})
    nodes.append({"type": "OUTPUT", "id": "Cout", "params": {"width": 1}})

    for i in range(4):
        nodes.append({"type": "module", "id": f"fa{i}", "module": "FULLADD"})

    wires.append({"src": "Cin", "dst": ["fa0.Cin"]})

    for i in range(4):
        wires.append({"src": f"A{i}", "dst": [f"fa{i}.A"]})
        wires.append({"src": f"B{i}", "dst": [f"fa{i}.B"]})
        wires.append({"src": f"fa{i}.Sum", "dst": [f"S{i}.in"]})
        if i < 3:
            wires.append({"src": f"fa{i}.Cout", "dst": [f"fa{i+1}.Cin"]})
        else:
            wires.append({"src": f"fa{i}.Cout", "dst": ["Cout.in"]})

    return {"nodes": nodes, "wires": wires}


# ============================================================
# Simulator 类
# ============================================================

class Simulator:
    def __init__(self, circuit: Circuit):
        self.circuit = circuit
        self.traces: Dict[str, List[Tuple[int, Signal]]] = defaultdict(list)
        self.signal_history: List[Dict[str, Signal]] = []
        self.time = 0
        self.clock_cycles = 0
        self._snapshot_state()
        self.timing_analyzer = TimingAnalyzer(circuit)

    def _snapshot_state(self):
        snapshot = {}
        for node_id, node in self.circuit.nodes.items():
            for port_name, port in node.outputs.items():
                key = f"{node_id}.{port_name}"
                snapshot[key] = port.signal.copy()
            for port_name, port in node.inputs.items():
                key = f"{node_id}.{port_name}"
                snapshot[key] = port.signal.copy()
        self.signal_history.append(snapshot)

    def set_input(self, name: str, value: SignalValue):
        self.circuit.set_input(name, value)
        self.time += 1

    def run(self):
        iters = self.circuit.evaluate_combinational()
        self.time += 1
        self._snapshot_state()
        return iters

    def clock(self, cycles: int = 1):
        for _ in range(cycles):
            self.circuit.run_clock()
            self.clock_cycles += 1
            self.time += 1
            self._snapshot_state()

    def trace(self, signal_name: str):
        parts = signal_name.split('.')
        if len(parts) == 1:
            node_id = parts[0]
            port_name = 'out' if node_id in self.circuit.input_nodes else 'in'
        else:
            node_id, port_name = parts[0], parts[1]

        value = self.circuit.get_signal_value(node_id, port_name)
        if value is not None:
            self.traces[signal_name].append((self.time, value))

    def get_traced_signal(self, signal_name: str, cycle_idx: int) -> Optional[Signal]:
        if cycle_idx >= len(self.signal_history):
            return None
        snap = self.signal_history[cycle_idx]

        parts = signal_name.split('.')
        if len(parts) == 1:
            node_id = parts[0]
            for key in snap:
                if key.startswith(node_id + '.'):
                    return snap[key]
            return None
        key = signal_name
        if key in snap:
            return snap[key]
        return None

    def dump_waveform(self, signals: List[str], num_cycles: Optional[int] = None) -> str:
        if num_cycles is None:
            num_cycles = len(self.signal_history)
        num_cycles = min(num_cycles, len(self.signal_history))

        lines = []
        header = f"{'Signal':<20} |"
        for i in range(num_cycles):
            header += f" {i:>3} "
        lines.append(header)
        lines.append('-' * len(header))

        for sig in signals:
            values = []
            for i in range(num_cycles):
                val = self.get_traced_signal(sig, i)
                if val is None:
                    values.append(' ? ')
                elif val.width == 1:
                    values.append(f" {val[0]} ")
                else:
                    values.append(f"{val.to_int():>3}")
            line = f"{sig:<20} |" + ''.join(values)
            lines.append(line)

        return '\n'.join(lines)

    def dump_ascii_waveform(self, signals: List[str], num_cycles: Optional[int] = None) -> str:
        if num_cycles is None:
            num_cycles = len(self.signal_history)
        num_cycles = min(num_cycles, len(self.signal_history))

        lines = []
        time_axis = ' ' * 10
        for i in range(num_cycles):
            time_axis += str(i % 10)
        lines.append(time_axis)

        for sig in signals:
            values = []
            for i in range(num_cycles):
                val = self.get_traced_signal(sig, i)
                if val is None:
                    values.append(None)
                elif val.width == 1:
                    values.append(val[0])
                else:
                    values.append(val.to_int())

            wave_line = f"{sig:<9}|"
            prev = None
            for v in values:
                if v is None:
                    wave_line += 'x'
                elif isinstance(v, int) and v in [0, 1]:
                    if prev == v:
                        wave_line += '_' if v == 0 else '-'
                    else:
                        wave_line += '/' if v == 1 else '\\'
                    prev = v
                else:
                    wave_line += f"{v % 10}"
                    prev = None
            lines.append(wave_line)

        return '\n'.join(lines)

    def export_vcd(self, filepath: str, signals: List[str]):
        with open(filepath, 'w') as f:
            f.write("$date\n    Today\n$end\n")
            f.write("$version\n    Circuit Simulator VCD Export\n$end\n")
            f.write("$timescale\n    1ns\n$end\n")

            f.write("$scope module logic $end\n")
            sig_codes = {}
            for i, sig in enumerate(signals):
                code = chr(ord('!') + i)
                sig_codes[sig] = code
                parts = sig.split('.')
                name = parts[-1] if len(parts) > 1 else sig
                f.write(f"$var wire 1 {code} {name} $end\n")
            f.write("$upscope $end\n")
            f.write("$enddefinitions $end\n")

            f.write("#0\n")
            for sig in signals:
                val = self.get_traced_signal(sig, 0)
                code = sig_codes[sig]
                if val is None:
                    f.write(f"bx {code}\n")
                elif val.width == 1:
                    f.write(f"b{val[0]} {code}\n")
                else:
                    bits = ''.join(str(b) for b in reversed(val.bits))
                    f.write(f"b{bits} {code}\n")

            for t in range(1, len(self.signal_history)):
                changed = False
                for sig in signals:
                    prev_val = self.get_traced_signal(sig, t - 1)
                    cur_val = self.get_traced_signal(sig, t)
                    if prev_val != cur_val:
                        if not changed:
                            f.write(f"#{t * 10}\n")
                            changed = True
                        code = sig_codes[sig]
                        if cur_val is None:
                            f.write(f"bx {code}\n")
                        elif cur_val.width == 1:
                            f.write(f"b{cur_val[0]} {code}\n")
                        else:
                            bits = ''.join(str(b) for b in reversed(cur_val.bits))
                            f.write(f"b{bits} {code}\n")


# ============================================================
# 测试函数
# ============================================================

def test_adder4(sim: Simulator) -> bool:
    print("\n=== Testing 4-bit Ripple Carry Adder ===")
    passed = 0
    total = 0
    for a in range(16):
        for b in range(16):
            for cin in range(2):
                total += 1
                for i in range(4):
                    sim.set_input(f'A{i}', (a >> i) & 1)
                    sim.set_input(f'B{i}', (b >> i) & 1)
                sim.set_input('Cin', cin)
                sim.run()

                expected_sum = (a + b + cin) & 0xF
                expected_cout = 1 if (a + b + cin) > 15 else 0

                actual_sum = 0
                for i in range(4):
                    s = sim.circuit.get_output(f'S{i}')
                    actual_sum |= (s[0] << i)
                actual_cout = sim.circuit.get_output('Cout')[0]

                if actual_sum == expected_sum and actual_cout == expected_cout:
                    passed += 1
                else:
                    print(f"FAIL: A={a}, B={b}, Cin={cin} -> Sum={actual_sum}, Cout={actual_cout} (expected Sum={expected_sum}, Cout={expected_cout})")
    print(f"Adder4: {passed}/{total} tests passed")
    return passed == total


def test_decoder3to8(sim: Simulator) -> bool:
    print("\n=== Testing 3-to-8 Decoder ===")
    passed = 0
    total = 0
    for a in range(8):
        for en in range(2):
            total += 1
            for i in range(3):
                sim.set_input(f'A{i}', (a >> i) & 1)
            sim.set_input('EN', en)
            sim.run()

            for y in range(8):
                actual = sim.circuit.get_output(f'Y{y}')[0]
                expected = 1 if (en == 1 and y == a) else 0
                if actual != expected:
                    print(f"FAIL: A={a}, EN={en}, Y{y}={actual} (expected {expected})")
                else:
                    passed += 1
    print(f"Decoder3to8: {passed}/{total * 8} outputs correct ({passed // 8}/{total} test cases)")
    return passed == total * 8


def test_shiftreg8(sim: Simulator) -> bool:
    print("\n=== Testing 8-bit Shift Register ===")
    passed = 0
    total = 0

    sim.set_input('EN', 1)
    sim.set_input('DATA_IN', 0)
    sim.run()
    for _ in range(16):
        sim.clock()

    test_pattern = [1, 0, 1, 1, 0, 1, 0, 1]
    for bit in test_pattern:
        sim.set_input('DATA_IN', bit)
        sim.run()
        sim.clock()

    expected = list(reversed(test_pattern))
    for i in range(8):
        total += 1
        actual = sim.circuit.get_output(f'Q{i}')[0]
        expected_bit = expected[i]
        if actual == expected_bit:
            passed += 1
        else:
            print(f"FAIL: Q{i}={actual}, expected {expected_bit}")

    sim.set_input('EN', 0)
    sim.run()
    before_hold = [sim.circuit.get_output(f'Q{i}')[0] for i in range(8)]
    for _ in range(5):
        sim.clock()
    after_hold = [sim.circuit.get_output(f'Q{i}')[0] for i in range(8)]
    total += 1
    if before_hold == after_hold:
        passed += 1
    else:
        print(f"FAIL: Hold mode failed. Before={before_hold}, After={after_hold}")

    print(f"ShiftReg8: {passed}/{total} tests passed")
    return passed == total


def test_counter4(sim: Simulator) -> bool:
    print("\n=== Testing 4-bit Counter ===")
    passed = 0
    total = 0

    sim.set_input('EN', 1)
    sim.run()
    sim.clock()

    for expected in range(1, 17):
        total += 1
        actual = 0
        for i in range(4):
            actual |= (sim.circuit.get_output(f'Q{i}')[0] << i)
        actual &= 0xF
        expected &= 0xF
        if actual == expected:
            passed += 1
        else:
            print(f"FAIL: Count={actual}, expected {expected}")
        sim.clock()

    print(f"Counter4: {passed}/{total} tests passed")
    return passed == total


PRESET_TESTS = {
    'adder4': test_adder4,
    'decoder3to8': test_decoder3to8,
    'shiftreg8': test_shiftreg8,
    'counter4': test_counter4,
}


def interactive_mode(sim: Simulator, registry: Optional[ModuleRegistry] = None):
    registry = registry or GLOBAL_MODULE_REGISTRY
    print("\n=== Circuit Simulator Interactive Mode ===")
    print("Commands:")
    print("  set <name> <value>       - Set input value")
    print("  run                      - Run combinational propagation")
    print("  clock [n]                - Advance n clock cycles")
    print("  trace <signal>           - Trace a signal")
    print("  show [name]              - Show output/signal value")
    print("  list                     - List all inputs, outputs, nodes")
    print("  dump <sigs> [n]          - Dump waveform")
    print("  wave <sigs> [n]          - ASCII waveform")
    print("  vcd <file> <sigs>        - Export VCD file")
    print("  test                     - Run preset tests")
    print("  reset                    - Reset simulation")
    print("  --- Module System ---")
    print("  module define <NAME> --file <FILE>  - Register module from JSON")
    print("  module list              - List all registered modules")
    print("  module export <NAME> [FILE]         - Export module JSON template")
    print("  --- Fault Injection ---")
    print("  fault stuck-at <NODE> <PORT> 0|1    - Inject stuck-at fault")
    print("  fault bridge <N1.P1> <N2.P2>        - Inject bridge fault (OR)")
    print("  fault list               - List all injected faults")
    print("  fault clear              - Clear all faults")
    print("  --- ATPG ---")
    print("  atpg stuck-at <NODE> <PORT> 0|1     - Generate test vector for SA fault")
    print("  atpg bridge <N1.P1> <N2.P2>         - Generate test vector for bridge")
    print("  --- Timing Analysis ---")
    print("  timing analyze           - Analyze critical paths")
    print("  timing set <GATE> <ns>   - Set gate delay (e.g. timing set AND 3)")
    print("  timing report [period]   - Full timing report with clock period")
    print("  help                     - Show this help")
    print("  quit/exit                - Exit")
    print()

    while True:
        try:
            line = input("sim> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        tokens = line.split()
        cmd = tokens[0].lower()

        try:
            if cmd in ('quit', 'exit'):
                break

            elif cmd == 'help':
                print("See full help above.")

            elif cmd == 'set':
                if len(tokens) < 3:
                    print("Usage: set <name> <value>")
                    continue
                name = tokens[1]
                val_str = tokens[2]
                if val_str.startswith('0b'):
                    val = int(val_str, 2)
                elif val_str.startswith('0x'):
                    val = int(val_str, 16)
                elif all(c in '01' for c in val_str) and len(val_str) > 1:
                    bits = [int(c) for c in reversed(val_str)]
                    sim.set_input(name, bits)
                    print(f"Set {name} = {val_str}")
                    continue
                else:
                    val = int(val_str)
                sim.set_input(name, val)
                print(f"Set {name} = {val}")

            elif cmd == 'run':
                iters = sim.run()
                print(f"Ran {iters} iterations")

            elif cmd == 'clock':
                n = 1
                if len(tokens) > 1:
                    n = int(tokens[1])
                sim.clock(n)
                print(f"Advanced {n} clock cycle(s)")

            elif cmd == 'trace':
                if len(tokens) < 2:
                    print("Usage: trace <signal>")
                    continue
                sig = tokens[1]
                sim.trace(sig)
                val = sim.traces[sig][-1][1] if sim.traces[sig] else '?'
                print(f"Tracing {sig} = {val}")

            elif cmd == 'show':
                if len(tokens) < 2:
                    for name, out_node in sim.circuit.output_nodes.items():
                        val = out_node.get_value()
                        print(f"  {name} = {val}")
                else:
                    name = tokens[1]
                    if name in sim.circuit.output_nodes:
                        val = sim.circuit.get_output(name)
                        print(f"  {name} = {val}")
                    elif name in sim.circuit.input_nodes:
                        node = sim.circuit.input_nodes[name]
                        val = node.outputs['out'].signal
                        print(f"  {name} = {val}")
                    else:
                        parts = name.split('.')
                        if len(parts) == 2:
                            val = sim.circuit.get_signal_value(parts[0], parts[1])
                            if val is not None:
                                print(f"  {name} = {val}")
                            else:
                                print(f"Signal {name} not found")
                        else:
                            print(f"Signal {name} not found")

            elif cmd == 'list':
                print("Inputs:")
                for name in sim.circuit.input_nodes:
                    w = sim.circuit.input_nodes[name].params['width']
                    print(f"  {name} (width={w})")
                print("Outputs:")
                for name in sim.circuit.output_nodes:
                    w = sim.circuit.output_nodes[name].params['width']
                    print(f"  {name} (width={w})")
                print("Nodes:")
                for nid, node in sim.circuit.nodes.items():
                    extra = ''
                    if node.type == 'MODULE':
                        extra = f" ({node.module_name})"
                    print(f"  {nid} [{node.type}]{extra}")

            elif cmd == 'dump':
                if len(tokens) < 2:
                    print("Usage: dump <sig1,sig2,...> [num_cycles]")
                    continue
                sigs = tokens[1].split(',')
                n = None
                if len(tokens) > 2:
                    n = int(tokens[2])
                print(sim.dump_waveform(sigs, n))

            elif cmd == 'wave':
                if len(tokens) < 2:
                    print("Usage: wave <sig1,sig2,...> [num_cycles]")
                    continue
                sigs = tokens[1].split(',')
                n = None
                if len(tokens) > 2:
                    n = int(tokens[2])
                print(sim.dump_ascii_waveform(sigs, n))

            elif cmd == 'vcd':
                if len(tokens) < 3:
                    print("Usage: vcd <file> <sig1,sig2,...>")
                    continue
                filepath = tokens[1]
                sigs = tokens[2].split(',')
                sim.export_vcd(filepath, sigs)
                print(f"VCD exported to {filepath}")

            elif cmd == 'test':
                for preset_name, test_fn in PRESET_TESTS.items():
                    circuit_json_fn = PRESET_CIRCUITS.get(preset_name)
                    if circuit_json_fn:
                        circuit_data = circuit_json_fn()
                        test_circuit = parse_circuit_from_json(circuit_data, registry)
                        test_sim = Simulator(test_circuit)
                        test_fn(test_sim)

            elif cmd == 'reset':
                sim.time = 0
                sim.clock_cycles = 0
                sim.signal_history = []
                sim.traces = defaultdict(list)
                sim._snapshot_state()
                print("Simulation reset")

            elif cmd == 'module':
                if len(tokens) < 2:
                    print("Usage: module <define|list|export> ...")
                    continue
                subcmd = tokens[1].lower()

                if subcmd == 'define':
                    if len(tokens) < 5:
                        print("Usage: module define <NAME> --file <FILE>")
                        continue
                    mod_name = tokens[2]
                    if tokens[3] == '--file':
                        filepath = tokens[4]
                        try:
                            defn = registry.define_from_json(mod_name, filepath)
                            print(f"Module '{defn.name}' registered.")
                            print(f"  {defn}")
                        except Exception as e:
                            print(f"Error defining module: {e}")
                    else:
                        print("Usage: module define <NAME> --file <FILE>")

                elif subcmd == 'list':
                    modules = registry.list_all()
                    if not modules:
                        print("No modules registered.")
                    else:
                        print(f"Registered modules ({len(modules)}):")
                        for m in modules:
                            print(f"  {m}")

                elif subcmd == 'export':
                    if len(tokens) < 3:
                        print("Usage: module export <NAME> [FILE]")
                        continue
                    name = tokens[2].upper()
                    data = None
                    if name == 'HALFADD':
                        data = create_halfadder_module_json()
                    elif name == 'FULLADD':
                        data = create_fulladder_module_json()
                    elif name == 'ADDER4':
                        data = create_adder4_module_json()
                    else:
                        mod = registry.get(name)
                        if mod:
                            data = {
                                'ports': mod.ports,
                                'nodes': mod.circuit_data['nodes'],
                                'wires': mod.circuit_data['wires'],
                            }
                    if data is None:
                        print(f"No template for module '{name}'")
                        continue
                    filepath = tokens[3] if len(tokens) > 3 else f"{name.lower()}.json"
                    with open(filepath, 'w') as f:
                        json.dump(data, f, indent=2)
                    print(f"Module '{name}' exported to {filepath}")

                else:
                    print(f"Unknown module subcommand: {subcmd}")

            elif cmd == 'fault':
                if len(tokens) < 2:
                    print("Usage: fault <stuck-at|bridge|list|clear> ...")
                    continue
                subcmd = tokens[1].lower()

                if subcmd == 'stuck-at':
                    if len(tokens) < 5:
                        print("Usage: fault stuck-at <NODE_ID> <PORT> 0|1")
                        continue
                    node_id = tokens[2]
                    port = tokens[3]
                    value = int(tokens[4])
                    sim.circuit.fault_manager.add_stuck_at(node_id, port, value)
                    print(f"Injected: {sim.circuit.fault_manager.list_faults()[-1]}")

                elif subcmd == 'bridge':
                    if len(tokens) < 4:
                        print("Usage: fault bridge <NODE1.PORT1> <NODE2.PORT2>")
                        continue
                    np1 = tokens[2].split('.')
                    np2 = tokens[3].split('.')
                    if len(np1) != 2 or len(np2) != 2:
                        print("Format: NODE.PORT (e.g. gate1.out)")
                        continue
                    sim.circuit.fault_manager.add_bridge(np1[0], np1[1], np2[0], np2[1])
                    print(f"Injected: {sim.circuit.fault_manager.list_faults()[-1]}")

                elif subcmd == 'list':
                    faults = sim.circuit.fault_manager.list_faults()
                    if not faults:
                        print("No faults injected.")
                    else:
                        print(f"Injected faults ({len(faults)}):")
                        for f in faults:
                            print(f"  {f}")

                elif subcmd == 'clear':
                    sim.circuit.fault_manager.clear()
                    print("All faults cleared.")

                else:
                    print(f"Unknown fault subcommand: {subcmd}")

            elif cmd == 'atpg':
                if len(tokens) < 2:
                    print("Usage: atpg <stuck-at|bridge> ...")
                    continue
                subcmd = tokens[1].lower()
                atpg = ATPG(sim.circuit, registry)
                result = None

                if subcmd == 'stuck-at':
                    if len(tokens) < 5:
                        print("Usage: atpg stuck-at <NODE_ID> <PORT> 0|1")
                        continue
                    node_id = tokens[2]
                    port = tokens[3]
                    value = int(tokens[4])
                    print(f"Generating test for stuck-at-{value} fault on {node_id}.{port}...")
                    result = atpg.generate_for_stuck_at(node_id, port, value)

                elif subcmd == 'bridge':
                    if len(tokens) < 4:
                        print("Usage: atpg bridge <NODE1.PORT1> <NODE2.PORT2>")
                        continue
                    np1 = tokens[2].split('.')
                    np2 = tokens[3].split('.')
                    if len(np1) != 2 or len(np2) != 2:
                        print("Format: NODE.PORT (e.g. gate1.out)")
                        continue
                    print(f"Generating test for bridge fault on {np1[0]}.{np1[1]} || {np2[0]}.{np2[1]}...")
                    result = atpg.generate_for_bridge(np1[0], np1[1], np2[0], np2[1])

                else:
                    print(f"Unknown atpg subcommand: {subcmd}")
                    continue

                if result is None:
                    print("Too many inputs (max 16 for exhaustive search)")
                elif not result['detected']:
                    print("No test vector found (fault may be undetectable)")
                else:
                    print("\n=== ATPG Result ===")
                    print(f"Test Vector:")
                    for inp_name in sorted(result['inputs'].keys()):
                        print(f"  {inp_name} = {result['inputs'][inp_name]}")
                    print(f"\nExpected Output Comparison:")
                    print(f"  {'Output':<10} {'Good':<10} {'Faulty':<10}")
                    print(f"  {'-'*30}")
                    for out_name in sorted(result['differences'].keys()):
                        g, b = result['differences'][out_name]
                        mark = " <-- DIFF"
                        print(f"  {out_name:<10} {str(g):<10} {str(b):<10}{mark}")
                    for out_name in sorted(result['good_outputs'].keys()):
                        if out_name not in result['differences']:
                            g = result['good_outputs'][out_name]
                            b = result['bad_outputs'].get(out_name, g)
                            print(f"  {out_name:<10} {str(g):<10} {str(b):<10}")

            elif cmd == 'timing':
                if len(tokens) < 2:
                    print("Usage: timing <analyze|set|report> ...")
                    continue
                subcmd = tokens[1].lower()

                if subcmd == 'analyze':
                    print("Running timing analysis...")
                    critical = sim.timing_analyzer.find_critical_path()
                    if critical:
                        print(f"\nCritical Path: {critical.describe()}")
                    all_paths = sim.timing_analyzer.analyze_all_paths()
                    if all_paths:
                        print(f"\nAll paths ({len(all_paths)}):")
                        for r in all_paths:
                            print(f"  {r.describe()}")
                    else:
                        print("No combinational paths found.")

                elif subcmd == 'set':
                    if len(tokens) < 4:
                        print("Usage: timing set <GATE_TYPE> <DELAY_NS>")
                        continue
                    gate_type = tokens[2].upper()
                    delay = float(tokens[3])
                    sim.timing_analyzer.set_delay(gate_type, delay)
                    print(f"Set {gate_type} delay = {delay:.1f}ns")

                elif subcmd == 'report':
                    period = None
                    if len(tokens) > 2:
                        period = float(tokens[2])
                    print(sim.timing_analyzer.generate_report(period))

                else:
                    print(f"Unknown timing subcommand: {subcmd}")

            else:
                print(f"Unknown command: {cmd}. Type 'help' for list.")

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description='Digital Logic Circuit Simulator')
    parser.add_argument('circuit', nargs='?', help='JSON circuit file or preset name')
    parser.add_argument('--interactive', '-i', action='store_true', help='Run in interactive mode')
    parser.add_argument('--test', action='store_true', help='Run preset circuit tests')
    parser.add_argument('--preset', help='Use preset circuit: adder4, shiftreg8, decoder3to8, counter4')

    args = parser.parse_args()

    if args.test:
        print("Running all preset circuit tests...")
        all_passed = True
        for preset_name, create_fn in PRESET_CIRCUITS.items():
            circuit_data = create_fn()
            try:
                circuit = parse_circuit_from_json(circuit_data, GLOBAL_MODULE_REGISTRY)
                sim = Simulator(circuit)
                test_fn = PRESET_TESTS.get(preset_name)
                if test_fn:
                    passed = test_fn(sim)
                    if not passed:
                        all_passed = False
            except Exception as e:
                print(f"Error testing {preset_name}: {e}")
                import traceback
                traceback.print_exc()
                all_passed = False
        print()
        if all_passed:
            print("ALL TESTS PASSED!")
        else:
            print("SOME TESTS FAILED!")
        sys.exit(0 if all_passed else 1)

    circuit_data = None
    circuit_name = args.circuit or args.preset

    if circuit_name:
        if circuit_name in PRESET_CIRCUITS:
            print(f"Using preset circuit: {circuit_name}")
            circuit_data = PRESET_CIRCUITS[circuit_name]()
        else:
            try:
                with open(circuit_name, 'r') as f:
                    circuit_data = json.load(f)
                print(f"Loaded circuit from: {circuit_name}")
            except FileNotFoundError:
                print(f"Error: File '{circuit_name}' not found and not a preset.")
                print(f"Available presets: {', '.join(PRESET_CIRCUITS.keys())}")
                sys.exit(1)
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON: {e}")
                sys.exit(1)
    else:
        print("Error: No circuit specified.")
        print("Usage: python circuit.py CIRCUIT.json [--interactive]")
        print(f"Presets: {', '.join(PRESET_CIRCUITS.keys())}")
        print("Or use --test to run preset tests.")
        sys.exit(1)

    try:
        circuit = parse_circuit_from_json(circuit_data, GLOBAL_MODULE_REGISTRY)
    except Exception as e:
        print(f"Error building circuit: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    has_comb_loop = False
    try:
        loops = circuit.detect_combinational_loops()
        if loops:
            has_comb_loop = True
            print(f"WARNING: Combinational loop detected: {' -> '.join(loops[0])}")
    except Exception:
        pass

    sim = Simulator(circuit)

    print(f"Circuit loaded: {len(circuit.nodes)} nodes, {len(circuit.wires)} wires")
    print(f"Inputs: {list(circuit.input_nodes.keys())}")
    print(f"Outputs: {list(circuit.output_nodes.keys())}")

    if args.interactive:
        interactive_mode(sim, GLOBAL_MODULE_REGISTRY)
    else:
        print("\nUse --interactive to enter interactive mode, or --test to run tests.")
        if has_comb_loop:
            print("Skipping example run due to combinational loop.")
        else:
            print("Example non-interactive usage:")
            for in_name in list(circuit.input_nodes.keys())[:3]:
                sim.set_input(in_name, 1)
            sim.run()
            print("\nSample outputs after setting some inputs to 1:")
            for out_name, out_node in circuit.output_nodes.items():
                val = out_node.get_value()
                print(f"  {out_name} = {val}")


if __name__ == '__main__':
    main()