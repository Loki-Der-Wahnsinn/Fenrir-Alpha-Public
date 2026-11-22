-- Read-only graph features for the same one-dimensional filtration as
-- topology_features.py. The caller supplies module names and directed edges.

local function array_length(value, name)
    if type(value) ~= "table" then
        error(name .. " must be an array", 3)
    end
    local count, maximum = 0, 0
    for key in pairs(value) do
        if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then
            error(name .. " must be a dense array", 3)
        end
        count = count + 1
        maximum = math.max(maximum, key)
    end
    if count ~= maximum then
        error(name .. " must be a dense array", 3)
    end
    return count
end

local function groups_for(vertices, outgoing, incoming)
    local visited, order = {}, {}
    for _, start in ipairs(vertices) do
        if not visited[start] then
            visited[start] = true
            local stack = {{name = start, index = 1}}
            while #stack > 0 do
                local frame = stack[#stack]
                local neighbor = outgoing[frame.name][frame.index]
                if neighbor then
                    frame.index = frame.index + 1
                    if not visited[neighbor] then
                        visited[neighbor] = true
                        stack[#stack + 1] = {name = neighbor, index = 1}
                    end
                else
                    order[#order + 1] = frame.name
                    stack[#stack] = nil
                end
            end
        end
    end

    visited = {}
    local groups = {}
    for i = #order, 1, -1 do
        local start = order[i]
        if not visited[start] then
            visited[start] = true
            local stack, group = {start}, {}
            while #stack > 0 do
                local name = table.remove(stack)
                group[#group + 1] = name
                for _, neighbor in ipairs(incoming[name]) do
                    if not visited[neighbor] then
                        visited[neighbor] = true
                        stack[#stack + 1] = neighbor
                    end
                end
            end
            if #group > 1 then
                table.sort(group)
                groups[#groups + 1] = group
            end
        end
    end
    table.sort(groups, function(a, b)
        for i = 1, math.min(#a, #b) do
            if a[i] ~= b[i] then return a[i] < b[i] end
        end
        return #a < #b
    end)
    return groups
end

local function analyze(input_vertices, input_edges)
    local vertex_count = array_length(input_vertices, "vertices")
    local edge_count = array_length(input_edges, "edges")
    local vertices, known, directed = {}, {}, {}
    for i = 1, vertex_count do
        local name = input_vertices[i]
        if type(name) ~= "string" then error("vertex names must be strings", 2) end
        if not known[name] then
            known[name] = true
            vertices[#vertices + 1] = name
            directed[name] = {}
        end
    end
    table.sort(vertices)

    local directed_count = 0
    for i = 1, edge_count do
        local edge = input_edges[i]
        if array_length(edge, "edge") ~= 2 then error("each edge needs two vertices", 2) end
        local source, target = edge[1], edge[2]
        if type(source) ~= "string" or type(target) ~= "string"
            or not known[source] or not known[target] or source == target then
            error("edges must connect two distinct known vertices", 2)
        end
        if not directed[source][target] then
            directed[source][target] = true
            directed_count = directed_count + 1
        end
    end

    local outgoing, incoming, weighted = {}, {}, {}
    for _, name in ipairs(vertices) do
        outgoing[name], incoming[name] = {}, {}
    end
    for _, source in ipairs(vertices) do
        for target in pairs(directed[source]) do
            outgoing[source][#outgoing[source] + 1] = target
            incoming[target][#incoming[target] + 1] = source
            if source < target or not directed[target][source] then
                local a, b = source, target
                if b < a then a, b = b, a end
                weighted[#weighted + 1] = {
                    scale = directed[target][source] and 1 or 2, a = a, b = b
                }
            end
        end
    end
    for _, name in ipairs(vertices) do
        table.sort(outgoing[name])
        table.sort(incoming[name])
    end
    table.sort(weighted, function(a, b)
        if a.scale ~= b.scale then return a.scale < b.scale end
        if a.a ~= b.a then return a.a < b.a end
        return a.b < b.b
    end)

    local parent, size = {}, {}
    for _, name in ipairs(vertices) do parent[name], size[name] = name, 1 end
    local function find(name)
        while parent[name] ~= name do
            parent[name] = parent[parent[name]]
            name = parent[name]
        end
        return name
    end

    local deaths, births, reciprocal, scale_one_deaths = {}, {}, 0, 0
    for _, edge in ipairs(weighted) do
        if edge.scale == 1 then reciprocal = reciprocal + 1 end
        local a, b = find(edge.a), find(edge.b)
        if a == b then
            births[#births + 1] = edge.scale
        else
            if size[a] < size[b] then a, b = b, a end
            parent[b] = a
            size[a] = size[a] + size[b]
            deaths[#deaths + 1] = edge.scale
            if edge.scale == 1 then scale_one_deaths = scale_one_deaths + 1 end
        end
    end
    local components = #vertices - #deaths
    return {
        modules = #vertices,
        directed_imports = directed_count,
        undirected_edges = #weighted,
        reciprocal_pairs = reciprocal,
        h0_deaths = deaths,
        h0_essential = components,
        h1_births_essential = births,
        circular_import_groups = groups_for(vertices, outgoing, incoming),
        components_by_scale = {
            ["0"] = #vertices,
            ["1"] = #vertices - scale_one_deaths,
            ["2"] = components,
        },
    }
end

return {analyze = analyze}
