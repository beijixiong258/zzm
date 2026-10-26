package zzm.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
public class CourseMember {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String courseId;
    private String userId;
    private String role;
    private Boolean archived;
}
