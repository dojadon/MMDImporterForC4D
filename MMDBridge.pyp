import c4d
import mmpy
import os

reload(mmpy)

PLUGIN_ID = 89013

def create_c4d_material(doc, pmx_material, textures, pmx_file_dir):
    mat = c4d.Material()
    mat[c4d.ID_BASELIST_NAME] = pmx_material.name.encode('utf-8')

    if 0 <= pmx_material.texture_id < len(textures):
        texture_path = pmx_file_dir + "\\" + textures[pmx_material.texture_id]

        if os.path.exists(texture_path):
            shader = c4d.BaseShader(c4d.Xbitmap)
            shader[c4d.BITMAPSHADER_FILENAME] = texture_path.encode('utf-8')
            mat[c4d.MATERIAL_COLOR_SHADER] = shader
            mat.InsertShader(shader)
    
    doc.InsertMaterial(mat)
    return mat

class PmxLoaderData(c4d.plugins.SceneLoaderData):
    def Identify(self, node, name, probe, size):
        return name.lower().endswith('.pmx') and probe[:3] == 'PMX'
    
    def Load(self, node, name, doc, filterflags, error, bt):
        with open(name, 'rb') as f:
            pmx_model = mmpy.create_pmx_model(f)
        
        pmx_file_dir = os.path.dirname(name)

        root = c4d.BaseObject(c4d.Onull)
        root[c4d.ID_BASELIST_NAME] = pmx_model.header.model_name.encode('utf-8')
        root[c4d.ID_BASEOBJECT_REL_SCALE] = c4d.Vector(10)
        doc.InsertObject(root)
        
        joints = self.add_joints(root, pmx_model)

        doc.SetActiveObject(joints[0])
        c4d.CallCommand(1019883) #Align
        
        for joint in joints:
            self.freeze_joint(joint)
        
        mesh = c4d.BaseObject(c4d.Onull)
        mesh[c4d.ID_BASELIST_NAME] = "Mesh"
        mesh.InsertUnder(root)

        for pmx_material in pmx_model.materials:
            obj = create_object_by_material(doc, pmx_material, , pmx_model, joints, pmx_file_dir)
            obj.InsertUnder(mesh)

        mesh = self.create_mesh(doc, pmx_model, pmx_file_dir)
        mesh.InsertUnder(root)
        self.create_weight_tag(mesh, pmx_model, joints)
        self.create_morph_tag(doc, mesh, pmx_model)

        c4d.EventAdd()
        return c4d.FILEERROR_NONE
    
    def create_object_by_material(self, doc, pmx_material, vertex_indices, pmx_model, joints, pmx_file_dir):
        distinct_index = list(set(vertex_indices))

        obj = c4d.PolygonObject(len(distinct_index), len(vertex_indices) / 3)
        obj.SetAllPoints([c4d.Vector(*pmx_model.vertices[i].pos) for i in distinct_index])
        obj[c4d.ID_BASELIST_NAME] = pmx_material.name.encode('utf-8')

        uv_tag = c4d.UVWTag(obj.GetPolygonCount())

        for i in range(obj.GetPolygonCount()):
            poly = c4d.CPolygon(*vertex_indices[i * 3: i * 3 + 3])
            obj.SetPolygon(i, poly)
        
            uv_list = []
            for j in range(3):
                v = pmx_model.vertices[vertex_indices[i * 3 + j]]
                uv_list.append(c4d.Vector(v.uv[0], v.uv[1], 0))
            uv_list.append(c4d.Vector(0))

            uv_tag.SetSlow(i, *uv_list)
        
        obj.InsertTag(uv_tag)

        mat = create_c4d_material(doc, pmx_material, pmx_model.textures, pmx_file_dir)

        mat_tag = c4d.TextureTag(5616)
        mat_tag[c4d.ID_BASELIST_NAME] = obj[c4d.ID_BASELIST_NAME]
        mat_tag[c4d.TEXTURETAG_MATERIAL] = mat
        mat_tag[c4d.TEXTURETAG_PROJECTION] = 6

        obj.InsertTag(mat_tag)

        tag = c4d.modules.character.CAWeightTag()
        obj.InsertTag(tag)

        for joint in joints:
            tag.AddJoint(joint)

        for i, vertex_index in enumerate(distinct_index):
            for bone_id, weight in pmx_model.vertices[vertex_index].weight:
                if weight > 0:
                    tag.SetWeight(bone_id, i, weight)

        skin = c4d.BaseObject(1019363)
        skin.InsertUnder(obj)

        obj.Message(c4d.MSG_UPDATE)

    def create_morph_tag(self, doc, obj, pmx_model):
        morph_tag = c4d.modules.character.CAPoseMorphTag()
        morph_tag[c4d.ID_CA_POSE_POINTS] = 1

        obj.InsertTag(morph_tag)

        morph_tag.InitMorphs()
        morph_tag.ExitEdit(doc, True)

        base_morph = morph_tag.AddMorph()
        base_morph.Store(doc, morph_tag, c4d.CAMORPH_DATA_FLAGS_POINTS | c4d.CAMORPH_DATA_FLAGS_ASTAG)

        for pmx_morph in pmx_model.morphs:
            if pmx_morph.morph_type == mmpy.PmxMorph.TYPE_VERTEX:
                self.create_vertex_morph(obj, pmx_model, pmx_morph)
            elif pmx_morph.morph_type == mmpy.PmxMorph.TYPE_GROUP:
                self.create_group_morph(obj, pmx_model, pmx_morph)

            morph = morph_tag.AddMorph()
            morph.SetName(pmx_morph.name.encode('utf-8'))

            morph.Store(doc, morph_tag, c4d.CAMORPH_DATA_FLAGS_POINTS | c4d.CAMORPH_DATA_FLAGS_ASTAG)

            morph_tag.UpdateMorphs()

            obj.SetAllPoints([c4d.Vector(*v.pos) for v in pmx_model.vertices])
        morph_tag.ExitEdit(doc, False)
    
    def create_vertex_morph(self, obj, pmx_model, pmx_morph, weight=1):
        for d in pmx_morph.morph_data:
            obj.SetPoint(d.index, obj.GetPoint(d.index) + c4d.Vector(*d.pos) * weight)
        
    def create_group_morph(self, obj, pmx_model, pmx_morph):
        for d in pmx_morph.morph_data:
            self.create_vertex_morph(obj, pmx_model, pmx_model.morphs[d.index], d.weight)

    def create_mesh(self, doc, pmx_model, pmx_file_dir):
        obj = c4d.PolygonObject(len(pmx_model.vertices), len(pmx_model.vertex_indices) / 3)
        obj.SetAllPoints([c4d.Vector(*v.pos) for v in pmx_model.vertices])
        obj[c4d.ID_BASELIST_NAME] = "Mesh"

        phong_tag = c4d.BaseTag(5612)
        phong_tag[c4d.PHONGTAG_PHONG_ANGLELIMIT] = 1
        phong_tag[c4d.PHONGTAG_PHONG_ANGLE] = 1.0471975511965976

        uv_tag = c4d.UVWTag(obj.GetPolygonCount())

        for i in range(obj.GetPolygonCount()):
            poly = c4d.CPolygon(*pmx_model.vertex_indices[i * 3: i * 3 + 3])
            obj.SetPolygon(i, poly)

            uv_list = []
            for j in range(3):
                v = pmx_model.vertices[pmx_model.vertex_indices[i * 3 + j]]
                uv_list.append(c4d.Vector(v.uv[0], v.uv[1], 0))
            uv_list.append(c4d.Vector(0))

            uv_tag.SetSlow(i, *uv_list)
        
        obj.InsertTag(phong_tag)
        obj.InsertTag(uv_tag)
        obj.Message(c4d.MSG_UPDATE)

        skin = c4d.BaseObject(1019363)
        skin.InsertUnder(obj)

        tag_list = [], []

        face_count = 0
        for material in pmx_model.materials:
            selection_tag = c4d.SelectionTag(c4d.Tpolygonselection)
            selection_tag[c4d.ID_BASELIST_NAME] = material.name.encode('utf-8')
            selection_tag.GetBaseSelect().SelectAll(face_count +  + material.face_count / 3, face_count)
            
            mat = create_c4d_material(doc, material, pmx_model.textures, pmx_file_dir)

            mat_tag = c4d.TextureTag(5616)
            mat_tag[c4d.ID_BASELIST_NAME] = selection_tag[c4d.ID_BASELIST_NAME]
            mat_tag[c4d.TEXTURETAG_MATERIAL] = mat
            mat_tag[c4d.TEXTURETAG_RESTRICTION] = selection_tag[c4d.ID_BASELIST_NAME]
            mat_tag[c4d.TEXTURETAG_PROJECTION] = 6

            tag_list[0].append(selection_tag)
            tag_list[1].append(mat_tag)

            face_count += material.face_count / 3
        
        for l in tag_list:
            for tag in l:
                obj.InsertTag(tag, pred=phong_tag)

        return obj

    def create_weight_tag(self, obj, pmx_model, joints):
        tag = c4d.modules.character.CAWeightTag()
        obj.InsertTag(tag)

        for joint in joints:
            tag.AddJoint(joint)

        for i, vertex in enumerate(pmx_model.vertices):
            for bone_id, weight in vertex.weight:
                if weight > 0:
                    tag.SetWeight(bone_id, i, weight)
        
        return tag

    def add_joints(self, root, model):
        joints = []

        for bone in model.bones:
            joints.append(self.add_joint(root, joints, bone, model.bones))
        
        return joints
    
    def freeze_joint(self, joint):
        joint[c4d.ID_BASEOBJECT_FROZEN_POSITION] = joint[c4d.ID_BASEOBJECT_REL_POSITION]
        joint[c4d.ID_BASEOBJECT_REL_POSITION] = c4d.Vector(0)

        joint[c4d.ID_BASEOBJECT_FROZEN_ROTATION] = joint[c4d.ID_BASEOBJECT_REL_ROTATION]
        joint[c4d.ID_BASEOBJECT_REL_ROTATION] = c4d.Vector(0)

    
    def add_joint(self, root, joints, bone, bones):
        joint = c4d.modules.character.CAJointObject()
        joint[c4d.ID_BASELIST_NAME] = bone.name.encode('utf-8')
        joint[c4d.ID_BASEOBJECT_REL_POSITION] = c4d.Vector(*bone.pos)

        if not bone.flags & mmpy.PmxBone.FLAG_VISIBLE:
            joint.SetEditorMode(c4d.MODE_OFF)

        if bone.parent_id > -1:
            parent_bone = bones[bone.parent_id]

            joint[c4d.ID_BASEOBJECT_REL_POSITION] -= c4d.Vector(*parent_bone.pos)
            joint.InsertUnderLast(joints[bone.parent_id])

            if parent_bone.flags & mmpy.PmxBone.FLAG_OFFSET and bones[parent_bone.arrow_id] == bone:
                joint.InsertUnder(joints[bone.parent_id])
            else:
                joint.InsertUnderLast(joints[bone.parent_id])
        else:
            joint.InsertUnderLast(root)

        return joint

class VmdSaverData(c4d.plugins.SceneSaverData):
    def Save(self, node, name, doc, filterflags):
        print name

if __name__ == "__main__":
    c4d.plugins.RegisterSceneLoaderPlugin(id=PLUGIN_ID, str="Pmx File(*.pmx)", g=PmxLoaderData, info=c4d.PLUGINFLAG_SCENELOADER_MERGEORIGINAL, description="")
    c4d.plugins.RegisterSceneSaverPlugin(id=PLUGIN_ID + 1, str="Vmd Motion(*.vmd)", g=VmdSaverData, info=0, description="", suffix="vmd")