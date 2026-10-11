// Small CodeWalker.Core helper for build.py: read the textures out of a loose
// .ytd, and write a copy of a .ytd with one texture's pixel data swapped.
//
//   ytdtool info <file.ytd>
//       JSON: every texture's name, size, format, mip levels, stride, data length
//   ytdtool dump <file.ytd> <texture> <out.bgra>
//       the top mip decoded to 8-bit BGRA (width*height*4 bytes, no header)
//   ytdtool pack <template.ytd> <texture> <data.bin> <out.ytd>
//       the template with that texture's data block replaced by data.bin, which
//       must be exactly as long as the original (same format, size and mips --
//       only the pixels change, so the file stays one the game already accepts)
//   ytdtool fromdds <in.dds> <texture> <out.ytd>
//       a new .ytd holding that one texture (what build.py writes)
//   ytdtool rpfls <gta-folder> <file.rpf> [out-dir]
//       list what a loose .rpf holds (needs the game's keys for encrypted ones),
//       and with out-dir write each file out as a loose file
//   ytdtool yddmesh <file.ydd> <out.bin>
//       every triangle of a minimap vector tile (see vectors.py)
//   ytdtool yddinfo <file.ydd>
//       a vector tile's drawables, shaders and vertex layouts, as text

using System.Text;
using System.Text.Json;
using CodeWalker.GameFiles;
using CodeWalker.Utils;

if (args.Length < 2) return Usage();

switch (args[0])
{
    case "info":
    {
        var ytd = LoadYtd(args[1]);
        var list = new List<object>();
        foreach (var t in ytd.TextureDict.Textures.data_items)
        {
            list.Add(new
            {
                name = t.Name, width = (int)t.Width, height = (int)t.Height,
                format = t.Format.ToString(), levels = (int)t.Levels, stride = (int)t.Stride,
                dataLength = t.Data?.FullData?.Length ?? 0,
            });
        }
        Console.WriteLine(JsonSerializer.Serialize(list));
        return 0;
    }
    case "dump":
    {
        if (args.Length < 4) return Usage();
        var tex = Find(LoadYtd(args[1]), args[2]);
        var px = DDSIO.GetPixels(tex, 0);
        File.WriteAllBytes(args[3], px);
        Console.WriteLine($"{tex.Name} {tex.Width}x{tex.Height} -> {args[3]} ({px.Length} bytes)");
        return 0;
    }
    case "pack":
    {
        if (args.Length < 5) return Usage();
        var ytd = LoadYtd(args[1]);
        var tex = Find(ytd, args[2]);
        var data = File.ReadAllBytes(args[3]);
        if (data.Length != tex.Data.FullData.Length)
        {
            Console.Error.WriteLine($"data is {data.Length} bytes, {tex.Name} needs exactly {tex.Data.FullData.Length}");
            return 2;
        }
        tex.Data.FullData = data;
        File.WriteAllBytes(args[4], ytd.Save());

        // read it back: the new file has to load and decode like the old one
        var check = Find(LoadYtd(args[4]), args[2]);
        if (check.Data.FullData.Length != data.Length || DDSIO.GetPixels(check, 0) == null)
        {
            Console.Error.WriteLine($"{args[4]}: did not read back");
            return 3;
        }
        Console.WriteLine($"{args[4]} ({new FileInfo(args[4]).Length} bytes)");
        return 0;
    }
    case "fromdds":
    {
        // a new one-texture .ytd from a .dds, the way CodeWalker's own
        // "import DDS" builds one (YtdForm.OpenDDSFiles + BuildFromTextureList)
        if (args.Length < 4) return Usage();
        var tex = DDSIO.GetTexture(File.ReadAllBytes(args[1]));
        tex.Name = args[2];
        tex.NameHash = JenkHash.GenHash(args[2].ToLowerInvariant());
        var ytd = new YtdFile { TextureDict = new TextureDictionary() };
        ytd.TextureDict.BuildFromTextureList(new List<Texture> { tex });
        File.WriteAllBytes(args[3], ytd.Save());

        var check = Find(LoadYtd(args[3]), args[2]);
        if (DDSIO.GetPixels(check, 0) == null)
        {
            Console.Error.WriteLine($"{args[3]}: did not read back");
            return 3;
        }
        Console.WriteLine($"{args[3]} {check.Width}x{check.Height} {check.Format} levels={check.Levels} ({new FileInfo(args[3]).Length} bytes)");
        return 0;
    }
    case "rpfls":
    {
        if (args.Length < 3) return Usage();
        GTA5Keys.LoadFromPath(args[1], false);
        var rpf = new RpfFile(args[2], Path.GetFileName(args[2]));
        rpf.ScanStructure(s => { }, e => Console.Error.WriteLine("! " + e));
        Console.WriteLine($"encryption: {rpf.Encryption}");
        var outDir = args.Length > 3 ? args[3] : null;
        foreach (var e in rpf.AllEntries)
        {
            if (e is not RpfFileEntry fe) continue;
            Console.WriteLine($"{fe.Path}  {fe.FileSize}");
            if (outDir == null) continue;
            Directory.CreateDirectory(outDir);
            var data = rpf.ExtractFile(fe);
            if (fe is RpfResourceFileEntry rfe)
            {
                // a loose resource file carries its RSC7 header; the archive
                // keeps it in the entry instead (same as CodeWalker's export)
                data = ResourceBuilder.AddResourceHeader(rfe, ResourceBuilder.Compress(data));
            }
            File.WriteAllBytes(Path.Combine(outDir, fe.Name), data);
        }
        return 0;
    }
    case "yddmesh":
    {
        // every triangle of a minimap vector tile, for build.py to draw:
        //   per drawable: u32 nameHash, u32 geometryCount, then per geometry:
        //   u32 vertexCount, u32 stride, u32 declFlags, u32 indexCount,
        //   vertex bytes, u16 indices
        if (args.Length < 3) return Usage();
        var ydd = new YddFile();
        ydd.Load(File.ReadAllBytes(args[1]));
        using var w = new BinaryWriter(File.Create(args[2]));
        var dict = ydd.Dict ?? new Dictionary<uint, Drawable>();
        w.Write((uint)dict.Count);
        foreach (var (hash, d) in dict)
        {
            var geoms = (d.DrawableModels?.High ?? Array.Empty<DrawableModel>())
                .SelectMany(m => m.Geometries ?? Array.Empty<DrawableGeometry>()).ToArray();
            w.Write(hash);
            w.Write((uint)geoms.Length);
            foreach (var g in geoms)
            {
                var vb = g.VertexData.VertexBytes;
                var ib = g.IndexBuffer.Indices;
                w.Write((uint)g.VertexData.VertexCount);
                w.Write((uint)g.VertexData.VertexStride);
                w.Write((uint)g.VertexData.Info.Flags);
                w.Write((uint)ib.Length);
                w.Write(vb);
                foreach (var i in ib) w.Write(i);
            }
        }
        Console.WriteLine($"{args[2]}: {dict.Count} drawables");
        return 0;
    }
    case "yddinfo":
    {
        // what a minimap vector tile is made of: its shaders, their texture
        // and colour parameters, and whether its vertices carry colours
        var ydd = new YddFile();
        ydd.Load(File.ReadAllBytes(args[1]));
        foreach (var d in ydd.Drawables ?? Array.Empty<Drawable>())
        {
            Console.WriteLine($"drawable {d.Name}");
            foreach (var s in d.ShaderGroup?.Shaders?.data_items ?? Array.Empty<ShaderFX>())
            {
                var ps = new List<string>();
                var p = s.ParametersList;
                for (int i = 0; i < (p?.Count ?? 0); i++)
                {
                    var h = p.Hashes[i];
                    var v = p.Parameters[i].Data;
                    ps.Add(v is TextureBase tb ? $"{h}=tex:{tb.Name}" : v is SharpDX.Vector4[] arr ? $"{h}=[{string.Join(" ", arr)}]" : $"{h}={v}");
                }
                Console.WriteLine($"  shader {s.Name} ({s.FileName}) {string.Join(", ", ps)}");
            }
            var models = d.DrawableModels?.High ?? Array.Empty<DrawableModel>();
            foreach (var m in models)
            {
                foreach (var g in m.Geometries ?? Array.Empty<DrawableGeometry>())
                {
                    Console.WriteLine($"  geometry shader#{g.ShaderID} verts={g.VerticesCount} layout={g.VertexData?.Info?.Types} flags={g.VertexData?.Info?.Flags}");
                }
            }
        }
        return 0;
    }
}
return Usage();

static YtdFile LoadYtd(string path)
{
    var ytd = new YtdFile();
    ytd.Load(File.ReadAllBytes(path));
    if (ytd.TextureDict?.Textures?.data_items == null) throw new Exception($"{path}: no textures");
    return ytd;
}

static Texture Find(YtdFile ytd, string name)
{
    foreach (var t in ytd.TextureDict.Textures.data_items)
    {
        if (string.Equals(t.Name, name, StringComparison.OrdinalIgnoreCase)) return t;
    }
    throw new Exception($"no texture called {name}");
}

static int Usage()
{
    Console.Error.WriteLine("usage:\n  ytdtool info <file.ytd>\n  ytdtool dump <file.ytd> <texture> <out.bgra>\n" +
        "  ytdtool pack <template.ytd> <texture> <data.bin> <out.ytd>\n  ytdtool fromdds <in.dds> <texture> <out.ytd>\n" +
        "  ytdtool rpfls <gta-folder> <file.rpf> [out-dir]\n  ytdtool yddmesh <file.ydd> <out.bin>\n  ytdtool yddinfo <file.ydd>");
    return 1;
}
