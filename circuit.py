#!/usr/bin/env python3
import json
import sys
import argparse
from collections import defaultdict, deque
from typing import List, Dict, Tuple, Optional, Any, Union

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


class Circuit:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.wires: List[Wire] = []
        self.input_nodes: Dict[str, InputNode] = {}
        self.output_nodes: Dict[str, OutputNode] = {}
        self.sequential_nodes: List[Node] = []

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

        while iterations < max_iterations:
            iterations += 1
            changed = False

            for node in self.nodes.values():
                if node.is_edge_triggered():
                    continue
                node.evaluate()

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
                            changed = True

            if not changed:
                break

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


def parse_circuit_from_json(data: Dict[str, Any]) -> Circuit:
    circuit = Circuit()

    for node_data in data.get('nodes', []):
        node = create_node_from_json(node_data)
        circuit.add_node(node)

    for wire_data in data.get('wires', []):
        wire = create_wire_from_json(wire_data)
        circuit.add_wire(wire)

    return circuit


def create_node_from_json(node_data: Dict[str, Any]) -> Node:
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
    else:
        raise ValueError(f"Unknown node type: {node_type}")

    return node


def create_wire_from_json(wire_data: Dict[str, Any]) -> Wire:
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
            dst_port = 'in' if dst_node in [n.get('id') for n in []] else 'in'
            dst_port = 'in'
        dst_pairs.append((dst_node, dst_port))

    width = int(wire_data.get('width', 1))
    return Wire(src_node, src_port, dst_pairs, width)


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


class Simulator:
    def __init__(self, circuit: Circuit):
        self.circuit = circuit
        self.traces: Dict[str, List[Tuple[int, Signal]]] = defaultdict(list)
        self.signal_history: List[Dict[str, Signal]] = []
        self.time = 0
        self.clock_cycles = 0
        self._snapshot_state()

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


def interactive_mode(sim: Simulator):
    print("\n=== Circuit Simulator Interactive Mode ===")
    print("Commands:")
    print("  set <name> <value>       - Set input value (e.g. set A0 1, set BUS 1010)")
    print("  run                      - Run combinational propagation")
    print("  clock [n]                - Advance n clock cycles (default 1)")
    print("  trace <signal>           - Trace a signal (e.g. trace A0, trace dff0.Q)")
    print("  show [name]              - Show output/signal value")
    print("  list                     - List all inputs, outputs, nodes")
    print("  dump <sigs> [n]          - Dump waveform (comma-sep signals, n cycles)")
    print("  wave <sigs> [n]          - ASCII waveform")
    print("  vcd <file> <sigs>        - Export VCD file")
    print("  test                     - Run preset tests (if available)")
    print("  reset                    - Reset simulation")
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
                print("Commands: set, run, clock, trace, show, list, dump, wave, vcd, test, reset, help, quit")

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
                    print(f"  {nid} [{node.type}]")

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
                        test_circuit = parse_circuit_from_json(circuit_data)
                        test_sim = Simulator(test_circuit)
                        test_fn(test_sim)

            elif cmd == 'reset':
                sim.time = 0
                sim.clock_cycles = 0
                sim.signal_history = []
                sim.traces = defaultdict(list)
                sim._snapshot_state()
                print("Simulation reset")

            else:
                print(f"Unknown command: {cmd}. Type 'help' for list.")

        except Exception as e:
            print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(description='Digital Logic Circuit Simulator')
    parser.add_argument('circuit', nargs='?', help='JSON circuit file or preset name (adder4, shiftreg8, decoder3to8, counter4)')
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
                circuit = parse_circuit_from_json(circuit_data)
                sim = Simulator(circuit)
                test_fn = PRESET_TESTS.get(preset_name)
                if test_fn:
                    passed = test_fn(sim)
                    if not passed:
                        all_passed = False
            except Exception as e:
                print(f"Error testing {preset_name}: {e}")
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
        circuit = parse_circuit_from_json(circuit_data)
    except Exception as e:
        print(f"Error building circuit: {e}")
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
        interactive_mode(sim)
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
