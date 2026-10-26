package zzm.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
public class Course {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String code;
    private String title;
    private String description;
    private String ownerId;
    private String courseInformation;
    private String studentProfile;
    private String systemInstructions;
    private String joinCode;
    private Boolean archived;
    private Boolean workspace;
}
