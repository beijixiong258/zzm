package cn.aicademiya.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
public class AuthSession {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String userId;
    private java.time.LocalDateTime expiresAt;
}
